"""LeaseBreak.com scraper - NYC-specific sublet marketplace.

LeaseBreak's search page only shows address links without prices or details.
We extract listing URLs from the search page, then batch-scrape individual
listing pages via Firecrawl and parse each with the LLM.
"""

import logging
import re

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

# Max individual listing pages to scrape per borough per run
MAX_LISTINGS_PER_BOROUGH = 15

LISTING_URL_PATTERN = re.compile(
    r"https://www\.leasebreak\.com/short-term-rental-details/\d+/[\w-]+"
)


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
        client: FirecrawlClient,
        llm_parser: LLMParser,
        search_url: str,
    ) -> list[Listing]:
        """Scrape one borough: get search page, extract URLs, batch scrape details."""
        # Step 1: Get search page and extract listing URLs
        logger.info(f"Scraping LeaseBreak search: {search_url}")
        search_markdown = client.scrape_markdown(search_url, timeout=90.0)
        listing_urls = list(set(LISTING_URL_PATTERN.findall(search_markdown)))
        logger.info(f"  Found {len(listing_urls)} listing URLs")

        if not listing_urls:
            return []

        # Step 2: Take a limited sample
        urls_to_scrape = listing_urls[:MAX_LISTINGS_PER_BOROUGH]
        logger.info(f"  Batch scraping {len(urls_to_scrape)} individual listings")

        # Step 3: Batch scrape individual pages
        url_to_markdown = client.batch_scrape_markdown(
            urls_to_scrape, timeout=300.0
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
