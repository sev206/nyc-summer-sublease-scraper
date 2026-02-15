"""SpareRoom.com scraper - rooms for rent and sublets."""

import logging

from models.enums import ListingSource, ListingType
from models.listing import Listing
from parsers.llm_parser import LLMParser, listing_from_parsed
from scrapers.base import BaseScraper
from scrapers.firecrawl_client import FirecrawlClient

logger = logging.getLogger(__name__)

SPAREROOM_URL = (
    "https://www.spareroom.com/flatshare/index.cgi"
    "?search_id=&flatshare_type=offered&published_by=private_landlord"
    "&location_type=area&search_results=&editing=&"
    "max_rent=2000&per=pcm&available_search=N&day_avail=01&mon_avail=07&year_avail=2026"
    "&max_per_flat_default=&min_term=0&max_term=0&days_of_wk_available=7days"
    "&showme_1bed=Y&showme_rooms=Y&showme_buddyup=Y"
    "&where=New+York&search=Search"
)


class SpareRoomScraper(BaseScraper):
    source_name = "SpareRoom"

    def scrape(self) -> list[Listing]:
        if not self.settings.firecrawl_api_key:
            logger.warning("No Firecrawl API key configured, skipping SpareRoom")
            return []

        if not self.settings.anthropic_api_key:
            logger.warning("No Anthropic API key configured, skipping SpareRoom")
            return []

        client = FirecrawlClient(self.settings.firecrawl_api_key)
        llm_parser = LLMParser(self.settings.anthropic_api_key)
        listings = []

        try:
            logger.info("Scraping SpareRoom NYC listings")
            markdown = client.scrape_markdown(SPAREROOM_URL, timeout=90.0)
            parsed_listings = llm_parser.parse_listings_page(
                markdown, "SpareRoom NYC Rooms & Sublets", max_chars=25000
            )
            for parsed in parsed_listings:
                listing = listing_from_parsed(
                    parsed,
                    ListingSource.SPAREROOM,
                    default_type=ListingType.ROOM_IN_SHARED,
                )
                listings.append(listing)
        except Exception as e:
            logger.error(f"Failed to scrape SpareRoom: {e}")

        logger.info(f"SpareRoom: {len(listings)} listings scraped")
        return listings
