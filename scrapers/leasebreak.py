"""LeaseBreak.com scraper — NYC-specific sublet marketplace."""

import logging
import re
from datetime import date
from typing import Optional

from config.neighborhoods import get_borough, normalize_neighborhood
from models.enums import ListingSource, ListingType
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

# LeaseBreak URLs for NYC sublets under $2,200
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

        client = FirecrawlClient(self.settings.firecrawl_api_key)
        listings = []

        for url in LEASEBREAK_URLS:
            try:
                logger.info(f"Scraping LeaseBreak: {url}")
                markdown = client.scrape_markdown(url, timeout=90.0)
                parsed = self._parse_listings_page(markdown, url)
                listings.extend(parsed)
            except Exception as e:
                logger.error(f"Failed to scrape {url}: {e}")

        logger.info(f"LeaseBreak: {len(listings)} listings scraped")
        return listings

    def _parse_listings_page(self, markdown: str, page_url: str) -> list[Listing]:
        """Parse LeaseBreak markdown output into Listing objects.

        LeaseBreak listings typically show structured cards with:
        - Price
        - Neighborhood
        - Apartment type
        - Available dates
        - Link to detail page
        """
        listings = []

        # Split by listing boundaries — LeaseBreak uses consistent formatting
        # Each listing is typically separated by horizontal rules or headers
        sections = re.split(r"\n(?=#{1,3}\s|\*\*\$)", markdown)

        for section in sections:
            if len(section.strip()) < 20:
                continue

            listing = self._parse_section(section, page_url)
            if listing:
                listings.append(listing)

        return listings

    def _parse_section(self, section: str, page_url: str) -> Optional[Listing]:
        """Parse a single listing section from markdown."""
        # Extract price
        price = extract_price_from_text(section)

        # Extract neighborhood
        neighborhood, borough = extract_neighborhood(section)

        # Extract listing type
        listing_type = detect_listing_type(section)
        apartment_details = extract_apartment_details(section)
        is_furnished = extract_furnished(section)

        # Try to extract a link to the detail page
        link_match = re.search(r"\[.*?\]\((https?://[^\)]+leasebreak[^\)]+)\)", section)
        source_url = link_match.group(1) if link_match else page_url

        # Extract dates
        available_from = None
        available_to = None
        date_patterns = [
            r"(?:available|move.?in|start)\s*:?\s*(\w+\s+\d{1,2})",
            r"(?:until|through|end)\s*:?\s*(\w+\s+\d{1,2})",
        ]
        from_match = re.search(date_patterns[0], section, re.IGNORECASE)
        to_match = re.search(date_patterns[1], section, re.IGNORECASE)
        if from_match:
            available_from = parse_date(from_match.group(1))
        if to_match:
            available_to = parse_date(to_match.group(1))

        # Build description from first 300 chars of section
        description = re.sub(r"\[.*?\]\(.*?\)", "", section)  # Remove markdown links
        description = re.sub(r"[#*_\[\]()]", "", description).strip()[:300]

        if not price and not neighborhood:
            return None

        return Listing(
            source=ListingSource.LEASEBREAK,
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
