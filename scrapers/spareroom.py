"""SpareRoom.com scraper — rooms for rent and sublets."""

import logging
import re
from typing import Optional

from config.neighborhoods import get_borough, normalize_neighborhood
from models.enums import ListingSource, ListingType
from models.listing import Listing
from parsers.date_parser import parse_date
from parsers.location_parser import extract_neighborhood
from parsers.price_parser import extract_price_from_text
from parsers.structured_parser import extract_furnished
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

        client = FirecrawlClient(self.settings.firecrawl_api_key)
        listings = []

        try:
            logger.info("Scraping SpareRoom NYC listings")
            markdown = client.scrape_markdown(SPAREROOM_URL, timeout=90.0)
            listings = self._parse_listings_page(markdown)
        except Exception as e:
            logger.error(f"Failed to scrape SpareRoom: {e}")

        logger.info(f"SpareRoom: {len(listings)} listings scraped")
        return listings

    def _parse_listings_page(self, markdown: str) -> list[Listing]:
        """Parse SpareRoom markdown into Listing objects."""
        listings = []

        # SpareRoom listings are typically card-based with price, location, description
        sections = re.split(r"\n(?=#{1,3}\s|\*\*\$|\d+\.\s)", markdown)

        for section in sections:
            if len(section.strip()) < 30:
                continue

            listing = self._parse_section(section)
            if listing:
                listings.append(listing)

        return listings

    def _parse_section(self, section: str) -> Optional[Listing]:
        """Parse a single SpareRoom listing section."""
        price = extract_price_from_text(section)
        neighborhood, borough = extract_neighborhood(section)
        is_furnished = extract_furnished(section)

        # SpareRoom links
        link_match = re.search(r"\[.*?\]\((https?://[^\)]*spareroom[^\)]+)\)", section)
        source_url = link_match.group(1) if link_match else ""

        # Extract dates
        available_from = None
        date_match = re.search(
            r"(?:available|from)\s*:?\s*(\d{1,2}\s+\w+|\w+\s+\d{1,2})",
            section,
            re.IGNORECASE,
        )
        if date_match:
            available_from = parse_date(date_match.group(1))

        description = re.sub(r"\[.*?\]\(.*?\)", "", section)
        description = re.sub(r"[#*_\[\]()]", "", description).strip()[:300]

        if not price and not neighborhood:
            return None

        # SpareRoom is primarily rooms
        listing_type = ListingType.ROOM_IN_SHARED
        if any(w in section.lower() for w in ["studio", "1 bed", "one bed", "1br"]):
            listing_type = ListingType.STUDIO if "studio" in section.lower() else ListingType.ONE_BEDROOM

        return Listing(
            source=ListingSource.SPAREROOM,
            source_url=source_url,
            price_monthly=price,
            neighborhood=neighborhood,
            borough=borough,
            listing_type=listing_type,
            is_furnished=is_furnished,
            available_from=available_from,
            description=description,
            raw_text=section[:500],
        )
