"""Roomi scraper - roommate and sublet matching."""

import logging

from models.enums import ListingSource, ListingType
from models.listing import Listing
from parsers.llm_parser import LLMParser, listing_from_parsed
from scrapers.base import BaseScraper
from scrapers.firecrawl_client import FirecrawlClient

logger = logging.getLogger(__name__)

ROOMI_URL = "https://roomi.com/rooms-for-rent/new-york-ny"


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

        try:
            logger.info("Scraping Roomi NYC listings")
            markdown = client.scrape_markdown(ROOMI_URL, timeout=90.0)
            parsed_listings = llm_parser.parse_listings_page(
                markdown, "Roomi NYC Rooms & Sublets"
            )
            for parsed in parsed_listings:
                listing = listing_from_parsed(
                    parsed,
                    ListingSource.ROOMI,
                    default_type=ListingType.ROOM_IN_SHARED,
                )
                listings.append(listing)
        except Exception as e:
            logger.error(f"Failed to scrape Roomi: {e}")

        logger.info(f"Roomi: {len(listings)} listings scraped")
        return listings
