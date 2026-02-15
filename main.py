"""NYC Apartment Sublet Scraper — Pipeline Orchestrator.

Usage:
    python main.py                     # Run all scrapers
    python main.py --source craigslist # Run a single source
    python main.py --source facebook   # Run Facebook groups only
    python main.py --dry-run           # Scrape and score but don't write to sheet
"""

import argparse
import logging
import sys
from datetime import datetime

from config.settings import Settings
from dedup.deduplicator import Deduplicator
from models.listing import Listing
from scoring.rating import compute_rating
from sheets.client import get_gspread_client, open_spreadsheet
from sheets.sync import SheetSync

logger = logging.getLogger("apartment_scraper")

# Source name → scraper class import path
SCRAPER_REGISTRY: dict[str, type] = {}


def register_scrapers() -> None:
    """Lazy-import and register all scraper classes."""
    from scrapers.craigslist import CraigslistScraper

    SCRAPER_REGISTRY["craigslist"] = CraigslistScraper

    try:
        from scrapers.leasebreak import LeaseBreakScraper
        SCRAPER_REGISTRY["leasebreak"] = LeaseBreakScraper
    except ImportError:
        pass

    try:
        from scrapers.spareroom import SpareRoomScraper
        SCRAPER_REGISTRY["spareroom"] = SpareRoomScraper
    except ImportError:
        pass

    try:
        from scrapers.furnished_finder import FurnishedFinderScraper
        SCRAPER_REGISTRY["furnished_finder"] = FurnishedFinderScraper
    except ImportError:
        pass

    try:
        from scrapers.listings_project import ListingsProjectScraper
        SCRAPER_REGISTRY["listings_project"] = ListingsProjectScraper
    except ImportError:
        pass

    try:
        from scrapers.facebook_groups import FacebookGroupsScraper
        SCRAPER_REGISTRY["facebook"] = FacebookGroupsScraper
    except ImportError:
        pass


def run_scraper_safe(scraper_class: type, settings: Settings) -> list[Listing]:
    """Run a scraper with error isolation."""
    name = scraper_class.__name__
    try:
        logger.info(f"Starting {name}")
        scraper = scraper_class(settings)
        results = scraper.scrape()
        logger.info(f"{name} returned {len(results)} listings")
        return results
    except Exception as e:
        logger.error(f"{name} FAILED: {type(e).__name__}: {e}", exc_info=True)
        return []


def validate_listing(listing: Listing) -> bool:
    """Reject listings that are clearly invalid."""
    # Price sanity
    if listing.price_monthly is not None:
        if listing.price_monthly < 100 or listing.price_monthly > 15000:
            return False

    # Date sanity
    if listing.available_from and listing.available_from.year not in (2025, 2026):
        return False
    if listing.available_to and listing.available_to.year not in (2026, 2027):
        return False

    # Must have at least a URL or description
    if not listing.source_url and not listing.description and not listing.raw_text:
        return False

    return True


def filter_iso_posts(listings: list[Listing]) -> list[Listing]:
    """Filter out 'in search of' posts from Facebook."""
    filtered = []
    for listing in listings:
        text = (listing.raw_text or listing.description or "").lower()
        first_100 = text[:100]
        iso_patterns = [
            "iso", "in search of", "looking for", "seeking",
            "i need", "i'm looking", "im looking", "anyone know",
        ]
        if any(p in first_100 for p in iso_patterns):
            continue
        filtered.append(listing)
    return filtered


def main(source: str | None = None, dry_run: bool = False) -> None:
    settings = Settings()

    # Set up logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    register_scrapers()

    # Determine which scrapers to run
    if source:
        # Support comma-separated list of sources
        source_names = [s.strip() for s in source.split(",")]
        scrapers_to_run = {}
        for s in source_names:
            if s not in SCRAPER_REGISTRY:
                logger.error(
                    f"Unknown source '{s}'. Available: {list(SCRAPER_REGISTRY.keys())}"
                )
                sys.exit(1)
            scrapers_to_run[s] = SCRAPER_REGISTRY[s]
    else:
        scrapers_to_run = SCRAPER_REGISTRY

    # Phase 1: Scrape
    all_listings: list[Listing] = []
    for name, scraper_class in scrapers_to_run.items():
        listings = run_scraper_safe(scraper_class, settings)
        all_listings.extend(listings)

    logger.info(f"Total raw listings: {len(all_listings)}")

    # Phase 2: Filter ISO posts
    all_listings = filter_iso_posts(all_listings)
    logger.info(f"After ISO filter: {len(all_listings)}")

    # Phase 3: Validate
    all_listings = [l for l in all_listings if validate_listing(l)]
    logger.info(f"After validation: {len(all_listings)}")

    # Phase 4: Generate fingerprints
    for listing in all_listings:
        listing.id = listing.generate_fingerprint()

    # Phase 5: Deduplicate
    if not dry_run and settings.spreadsheet_id:
        gc = get_gspread_client(settings.google_sheets_credentials_file)
        spreadsheet = open_spreadsheet(gc, settings.spreadsheet_id)
        sheet_sync = SheetSync(spreadsheet)
        deduplicator = Deduplicator(sheet_sync)
    else:
        deduplicator = Deduplicator(sheet_sync=None)
        sheet_sync = None

    new_listings = deduplicator.deduplicate(all_listings)
    logger.info(f"After dedup: {len(new_listings)} new listings")

    # Phase 6: Score
    for listing in new_listings:
        rating, breakdown = compute_rating(listing, settings)
        listing.rating = rating
        listing.rating_breakdown = breakdown

    # Sort by rating
    new_listings.sort(key=lambda l: l.rating, reverse=True)

    # Phase 7: Write to sheet
    if dry_run:
        logger.info("DRY RUN - not writing to sheet")
        for l in new_listings[:20]:
            logger.info(
                f"  [{l.rating}] ${l.price_monthly} | {l.neighborhood} | "
                f"{l.listing_type.value} | {l.source.value}"
            )
    elif sheet_sync:
        added = sheet_sync.append_listings(new_listings)
        logger.info(f"Pipeline complete. Added {added} listings to sheet.")
    else:
        logger.warning("No spreadsheet configured. Set SPREADSHEET_ID in .env")

    logger.info(f"Run finished at {datetime.now().isoformat()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NYC Apartment Sublet Scraper")
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Run a single source (e.g., craigslist, facebook, leasebreak)",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help="Comma-separated list of sources (e.g., 'craigslist,leasebreak,spareroom')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and score but don't write to Google Sheets",
    )
    args = parser.parse_args()
    # --sources overrides --source
    source_arg = args.source
    if args.sources:
        source_arg = args.sources
    main(source=source_arg, dry_run=args.dry_run)
