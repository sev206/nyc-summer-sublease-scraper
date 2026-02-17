"""LeaseBreak.com scraper - NYC-specific sublet marketplace.

LeaseBreak's search page only shows address links without prices or details.
We extract listing URLs from the search page HTML using BeautifulSoup, then
fetch individual listing pages via Playwright and parse each with the LLM.
"""

import logging
import re

from bs4 import BeautifulSoup

from models.enums import ListingSource
from models.listing import Listing
from parsers.llm_parser import LLMParser, listing_from_parsed
from scrapers.base import BaseScraper
from scrapers.browser_client import BrowserClient

logger = logging.getLogger(__name__)

LEASEBREAK_URLS = [
    "https://www.leasebreak.com/listings?borough=Manhattan&max_price=2200",
    "https://www.leasebreak.com/listings?borough=Brooklyn&max_price=2200",
    "https://www.leasebreak.com/listings?borough=Queens&max_price=2200",
]

# Max individual listing pages to scrape per borough per run
MAX_LISTINGS_PER_BOROUGH = 50

# Captures (listing_id, slug) from listing URLs
LISTING_URL_PATTERN = re.compile(
    r"/short-term-rental-details/(\d+)/([\w-]+)"
)


class LeaseBreakScraper(BaseScraper):
    source_name = "LeaseBreak"

    def scrape(self) -> list[Listing]:
        if not self.settings.anthropic_api_key:
            logger.warning("No Anthropic API key configured, skipping LeaseBreak")
            return []

        llm_parser = LLMParser(self.settings.anthropic_api_key)
        listings = []

        with BrowserClient(delay_seconds=self.settings.scrape_delay_seconds) as client:
            for search_url in LEASEBREAK_URLS:
                try:
                    borough_listings = self._scrape_borough(
                        client, llm_parser, search_url
                    )
                    listings.extend(borough_listings)
                except Exception as e:
                    logger.error(f"Failed to scrape LeaseBreak {search_url}: {e}")

        logger.info(f"LeaseBreak: {len(listings)} listings scraped")
        return listings

    def _scrape_borough(
        self,
        client: BrowserClient,
        llm_parser: LLMParser,
        search_url: str,
    ) -> list[Listing]:
        """Scrape one borough: get search page, extract URLs, fetch details."""
        # Step 1: Get search page and extract listing URLs from HTML
        logger.info(f"Scraping LeaseBreak search: {search_url}")
        search_html = client.fetch_html(search_url, timeout=60.0)

        if not search_html:
            logger.warning(f"  Empty response from {search_url}")
            return []

        soup = BeautifulSoup(search_html, "html.parser")
        links = soup.select('a[href*="short-term-rental-details"]')

        # Extract (listing_id, slug) pairs, deduplicate by ID
        seen_ids: set[str] = set()
        unique_matches: list[tuple[str, str]] = []
        for link in links:
            href = link.get("href", "")
            m = LISTING_URL_PATTERN.search(href)
            if m:
                listing_id, slug = m.group(1), m.group(2)
                if listing_id not in seen_ids:
                    seen_ids.add(listing_id)
                    unique_matches.append((listing_id, slug))

        logger.info(f"  Found {len(unique_matches)} unique listing URLs")

        if not unique_matches:
            return []

        # Step 2: Sort by listing ID descending (newest first), take top N
        unique_matches.sort(key=lambda m: int(m[0]), reverse=True)
        top_matches = unique_matches[:MAX_LISTINGS_PER_BOROUGH]
        urls_to_scrape = [
            f"https://www.leasebreak.com/short-term-rental-details/{lid}/{slug}"
            for lid, slug in top_matches
        ]

        # Filter out URLs we've already scraped in previous runs
        if self.known_urls:
            before = len(urls_to_scrape)
            urls_to_scrape = [u for u in urls_to_scrape if u not in self.known_urls]
            skipped = before - len(urls_to_scrape)
            if skipped:
                logger.info(f"  Skipped {skipped} already-known URLs")

        if not urls_to_scrape:
            logger.info("  All listings already known, nothing to scrape")
            return []

        logger.info(f"  Fetching {len(urls_to_scrape)} new listings")

        # Step 3: Fetch individual pages via Playwright
        url_to_markdown = client.batch_fetch_markdown(
            urls_to_scrape, timeout=30.0
        )
        logger.info(f"  Got {len(url_to_markdown)} page results")

        # Step 4: Parse each page with LLM
        listings = []
        for url, markdown in url_to_markdown.items():
            try:
                parsed_list = llm_parser.parse_listings_page(
                    markdown, "LeaseBreak NYC Sublet", max_chars=6000
                )
                for parsed in parsed_list:
                    listing = listing_from_parsed(parsed, ListingSource.LEASEBREAK)
                    # Override URL with the actual listing page URL
                    if not listing.source_url or listing.source_url == "":
                        listing.source_url = url
                    listings.append(listing)
            except Exception as e:
                logger.warning(f"  Failed to parse LeaseBreak page {url}: {e}")

        return listings
