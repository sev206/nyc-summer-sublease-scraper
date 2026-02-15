"""Listings Project scraper - curated weekly listings."""

import logging

from models.enums import ListingSource
from models.listing import Listing
from parsers.llm_parser import LLMParser, listing_from_parsed
from scrapers.base import BaseScraper
from scrapers.firecrawl_client import FirecrawlClient

logger = logging.getLogger(__name__)

LISTINGS_PROJECT_URL = "https://www.listingsproject.com/listings"


class ListingsProjectScraper(BaseScraper):
    source_name = "Listings Project"

    def scrape(self) -> list[Listing]:
        if not self.settings.firecrawl_api_key:
            logger.warning("No Firecrawl API key, skipping Listings Project")
            return []

        if not self.settings.anthropic_api_key:
            logger.warning("No Anthropic API key, skipping Listings Project")
            return []

        client = FirecrawlClient(self.settings.firecrawl_api_key)
        llm_parser = LLMParser(self.settings.anthropic_api_key)
        listings = []

        try:
            logger.info("Scraping Listings Project")
            markdown = client.scrape_markdown(LISTINGS_PROJECT_URL, timeout=90.0)
            parsed_listings = llm_parser.parse_listings_page(
                markdown, "Listings Project NYC Apartments"
            )
            for parsed in parsed_listings:
                listing = listing_from_parsed(parsed, ListingSource.LISTINGS_PROJECT)
                listings.append(listing)
        except Exception as e:
            logger.error(f"Failed to scrape Listings Project: {e}")

        logger.info(f"Listings Project: {len(listings)} listings scraped")
        return listings
