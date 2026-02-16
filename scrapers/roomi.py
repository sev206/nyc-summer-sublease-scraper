"""Roomi scraper - rooms for rent via roomiapp.com.

Roomi's site (built on Bubble.io) requires JS rendering. Listings are
organized by neighborhood — each page shows ~5-15 room listings with
price, type, bedrooms, dates, and location inline. We scrape priority
Manhattan neighborhood pages plus a few BK/Queens ones.
"""

import logging

from models.enums import ListingSource, ListingType
from models.listing import Listing
from parsers.llm_parser import LLMParser, listing_from_parsed
from scrapers.base import BaseScraper
from scrapers.firecrawl_client import FirecrawlClient, FirecrawlCreditError

logger = logging.getLogger(__name__)

# Priority neighborhood pages on roomiapp.com (highest-interest first)
ROOMI_NEIGHBORHOOD_URLS = [
    # Tier 1 — Midtown East area
    "https://roomiapp.com/rooms-for-rent/midtown-east-manhattan-nyc-new-york",
    "https://roomiapp.com/rooms-for-rent/murray-hill-manhattan-nyc-new-york",
    "https://roomiapp.com/rooms-for-rent/kips-bay-manhattan-nyc-new-york",
    # Tier 2 — LES / East Village
    "https://roomiapp.com/rooms-for-rent/lower-east-side-manhattan-nyc-new-york",
    "https://roomiapp.com/rooms-for-rent/east-village-manhattan-nyc-new-york",
    # Tier 3 — Other Midtown / Downtown
    "https://roomiapp.com/rooms-for-rent/midtown-manhattan-manhattan-nyc-new-york",
    "https://roomiapp.com/rooms-for-rent/hells-kitchen-manhattan-nyc-new-york",
    "https://roomiapp.com/rooms-for-rent/chelsea-manhattan-nyc-new-york",
    "https://roomiapp.com/rooms-for-rent/gramercy-park-manhattan-nyc-new-york",
    "https://roomiapp.com/rooms-for-rent/greenwich-village-manhattan-nyc-new-york",
    "https://roomiapp.com/rooms-for-rent/financial-district-manhattan-nyc-new-york",
    # Tier 4 — UES
    "https://roomiapp.com/rooms-for-rent/upper-east-side-manhattan-nyc-new-york",
    # Tier 5 — BK / Queens
    "https://roomiapp.com/rooms-for-rent/williamsburg-brooklyn-nyc-new-york",
    "https://roomiapp.com/rooms-for-rent/long-island-city-queens-nyc-new-york",
    "https://roomiapp.com/rooms-for-rent/astoria-queens-nyc-new-york",
]

# JS wait time in ms — Roomi is built on Bubble.io and needs time to render
ROOMI_WAIT_FOR_MS = 5000


class RoomiScraper(BaseScraper):
    source_name = "Roomi"

    def scrape(self) -> list[Listing]:
        if not self.settings.firecrawl_api_key:
            logger.warning("No Firecrawl API key, skipping Roomi")
            return []

        if not self.settings.anthropic_api_key:
            logger.warning("No Anthropic API key, skipping Roomi")
            return []

        client = FirecrawlClient(self.settings.firecrawl_api_key)
        llm_parser = LLMParser(self.settings.anthropic_api_key)
        listings = []

        for url in ROOMI_NEIGHBORHOOD_URLS:
            try:
                neighborhood = url.split("/rooms-for-rent/")[1].split("-manhattan-")[0]
                logger.info(f"Scraping Roomi: {neighborhood}")
                markdown = client.scrape_markdown(
                    url, timeout=90.0, wait_for=ROOMI_WAIT_FOR_MS
                )
                if not markdown or len(markdown) < 200:
                    logger.warning(f"  Roomi page too short ({len(markdown)} chars), skipping")
                    continue

                logger.info(f"  Got {len(markdown)} chars of markdown")
                parsed_listings = llm_parser.parse_listings_page(
                    markdown, "Roomi NYC Room Listing", max_chars=12000
                )
                for parsed in parsed_listings:
                    listing = listing_from_parsed(
                        parsed,
                        ListingSource.ROOMI,
                        default_type=ListingType.ROOM_IN_SHARED,
                    )
                    if not listing.source_url or listing.source_url == "":
                        listing.source_url = url
                    listings.append(listing)

                logger.info(f"  Parsed {len(parsed_listings)} listings")
            except FirecrawlCreditError:
                logger.error("Firecrawl credits exhausted, stopping Roomi")
                break
            except Exception as e:
                logger.error(f"Failed to scrape Roomi {url}: {e}")

        logger.info(f"Roomi: {len(listings)} listings scraped")
        return listings
