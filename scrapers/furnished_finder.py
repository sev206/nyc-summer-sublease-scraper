"""Furnished Finder scraper - furnished short-term rentals."""

import logging

from models.enums import ListingSource
from models.listing import Listing
from parsers.llm_parser import LLMParser, listing_from_parsed
from scrapers.base import BaseScraper
from scrapers.firecrawl_client import FirecrawlClient

logger = logging.getLogger(__name__)

FURNISHED_FINDER_URL = "https://www.furnishedfinder.com/housing/New-York/New-York"


class FurnishedFinderScraper(BaseScraper):
    source_name = "Furnished Finder"

    def scrape(self) -> list[Listing]:
        if not self.settings.firecrawl_api_key:
            logger.warning("No Firecrawl API key, skipping Furnished Finder")
            return []

        if not self.settings.anthropic_api_key:
            logger.warning("No Anthropic API key, skipping Furnished Finder")
            return []

        client = FirecrawlClient(self.settings.firecrawl_api_key)
        llm_parser = LLMParser(self.settings.anthropic_api_key)
        listings = []

        try:
            logger.info("Scraping Furnished Finder NYC listings")
            markdown = client.scrape_markdown(FURNISHED_FINDER_URL, timeout=90.0)
            parsed_listings = llm_parser.parse_listings_page(
                markdown, "Furnished Finder NYC Rentals"
            )
            for parsed in parsed_listings:
                listing = listing_from_parsed(
                    parsed,
                    ListingSource.FURNISHED_FINDER,
                    default_furnished=True,
                )
                listings.append(listing)
        except Exception as e:
            logger.error(f"Failed to scrape Furnished Finder: {e}")

        logger.info(f"Furnished Finder: {len(listings)} listings scraped")
        return listings
