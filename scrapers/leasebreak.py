"""LeaseBreak.com scraper - NYC-specific sublet marketplace."""

import logging

from models.enums import ListingSource
from models.listing import Listing
from parsers.llm_parser import LLMParser, listing_from_parsed
from scrapers.base import BaseScraper
from scrapers.firecrawl_client import FirecrawlClient

logger = logging.getLogger(__name__)

LEASEBREAK_URLS = [
    "https://www.leasebreak.com/listings?borough=Manhattan&max_price=2200",
    "https://www.leasebreak.com/listings?borough=Brooklyn&max_price=2200",
    "https://www.leasebreak.com/listings?borough=Queens&max_price=2200",
]


class LeaseBreakScraper(BaseScraper):
    source_name = "LeaseBreak"

    def scrape(self) -> list[Listing]:
        if not self.settings.firecrawl_api_key:
            logger.warning("No Firecrawl API key configured, skipping LeaseBreak")
            return []

        if not self.settings.anthropic_api_key:
            logger.warning("No Anthropic API key configured, skipping LeaseBreak")
            return []

        client = FirecrawlClient(self.settings.firecrawl_api_key)
        llm_parser = LLMParser(self.settings.anthropic_api_key)
        listings = []

        for url in LEASEBREAK_URLS:
            try:
                logger.info(f"Scraping LeaseBreak: {url}")
                markdown = client.scrape_markdown(url, timeout=90.0)
                parsed_listings = llm_parser.parse_listings_page(
                    markdown, "LeaseBreak NYC Sublets"
                )
                for parsed in parsed_listings:
                    listing = listing_from_parsed(parsed, ListingSource.LEASEBREAK)
                    listings.append(listing)
            except Exception as e:
                logger.error(f"Failed to scrape LeaseBreak {url}: {e}")

        logger.info(f"LeaseBreak: {len(listings)} listings scraped")
        return listings
