"""Listings Project scraper — curated weekly listings."""

import logging
import re
from typing import Optional

from config.neighborhoods import get_borough, normalize_neighborhood
from models.enums import ListingSource
from models.listing import Listing
from parsers.date_parser import parse_date
from parsers.location_parser import extract_neighborhood
from parsers.price_parser import extract_price_from_text
from parsers.structured_parser import (
    detect_listing_type,
    extract_apartment_details,
    extract_furnished,
)
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

        client = FirecrawlClient(self.settings.firecrawl_api_key)
        listings = []

        try:
            logger.info("Scraping Listings Project")
            markdown = client.scrape_markdown(LISTINGS_PROJECT_URL, timeout=90.0)
            listings = self._parse_listings_page(markdown)
        except Exception as e:
            logger.error(f"Failed to scrape Listings Project: {e}")

        logger.info(f"Listings Project: {len(listings)} listings scraped")
        return listings

    def _parse_listings_page(self, markdown: str) -> list[Listing]:
        """Parse Listings Project markdown into Listing objects."""
        listings = []
        sections = re.split(r"\n(?=#{1,3}\s|\*\*\$|\-{3,})", markdown)

        for section in sections:
            if len(section.strip()) < 30:
                continue

            # Filter to NYC area listings only
            lower = section.lower()
            nyc_indicators = [
                "new york", "nyc", "manhattan", "brooklyn", "queens",
                "bronx", "midtown", "downtown", "uptown", "east village",
                "west village", "soho", "tribeca", "chelsea", "harlem",
                "williamsburg", "bushwick", "les", "ues", "uws",
            ]
            if not any(ind in lower for ind in nyc_indicators):
                continue

            listing = self._parse_section(section)
            if listing:
                listings.append(listing)

        return listings

    def _parse_section(self, section: str) -> Optional[Listing]:
        """Parse a single Listings Project listing."""
        price = extract_price_from_text(section)
        neighborhood, borough = extract_neighborhood(section)
        listing_type = detect_listing_type(section)
        apartment_details = extract_apartment_details(section)
        is_furnished = extract_furnished(section)

        link_match = re.search(
            r"\[.*?\]\((https?://[^\)]*listingsproject[^\)]+)\)", section
        )
        source_url = link_match.group(1) if link_match else ""

        available_from = None
        available_to = None
        avail_match = re.search(
            r"(?:available|from|starting)\s*:?\s*(\w+\s+\d{1,2})",
            section,
            re.IGNORECASE,
        )
        if avail_match:
            available_from = parse_date(avail_match.group(1))

        description = re.sub(r"\[.*?\]\(.*?\)", "", section)
        description = re.sub(r"[#*_\[\]()]", "", description).strip()[:300]

        if not price and not neighborhood:
            return None

        return Listing(
            source=ListingSource.LISTINGS_PROJECT,
            source_url=source_url,
            price_monthly=price,
            neighborhood=neighborhood,
            borough=borough,
            listing_type=listing_type,
            apartment_details=apartment_details,
            is_furnished=is_furnished,
            available_from=available_from,
            available_to=available_to,
            description=description,
            raw_text=section[:500],
        )
