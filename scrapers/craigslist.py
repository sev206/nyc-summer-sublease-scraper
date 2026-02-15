"""Craigslist NYC sublets scraper - direct HTML parsing."""

import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config.neighborhoods import get_borough, normalize_neighborhood
from models.enums import Borough, ListingSource, ListingType
from models.listing import Listing
from parsers.date_parser import extract_date_range
from parsers.location_parser import extract_neighborhood
from parsers.price_parser import parse_price
from parsers.structured_parser import (
    detect_listing_type,
    extract_apartment_details,
    extract_furnished,
)
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

CRAIGSLIST_URL = "https://newyork.craigslist.org/search/sub?max_price=2200"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class CraigslistScraper(BaseScraper):
    source_name = "Craigslist"

    def scrape(self) -> list[Listing]:
        listings = []

        try:
            logger.info(f"Scraping Craigslist: {CRAIGSLIST_URL}")
            response = httpx.get(
                CRAIGSLIST_URL,
                headers={"User-Agent": USER_AGENT},
                timeout=30.0,
                follow_redirects=True,
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select("li.cl-static-search-result")
            logger.info(f"Found {len(items)} Craigslist listings")

            for item in items[: self.settings.max_listings_per_source]:
                listing = self._parse_item(item)
                if listing:
                    listings.append(listing)

        except httpx.HTTPStatusError as e:
            logger.error(f"Craigslist HTTP error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Failed to scrape Craigslist: {e}")

        logger.info(f"Craigslist: {len(listings)} listings parsed")
        return listings

    def _parse_item(self, item) -> Optional[Listing]:
        """Parse a single Craigslist search result item."""
        # Extract link
        link_el = item.select_one("a")
        if not link_el:
            return None
        source_url = link_el.get("href", "")

        # Extract title
        title_el = item.select_one(".title")
        title = title_el.get_text(strip=True) if title_el else ""

        # Extract price
        price_el = item.select_one(".price")
        price_text = price_el.get_text(strip=True) if price_el else ""
        price = parse_price(price_text)

        # Extract location
        location_el = item.select_one(".location")
        location_text = location_el.get_text(strip=True) if location_el else ""

        # Normalize neighborhood
        if location_text:
            neighborhood = normalize_neighborhood(location_text)
            borough = get_borough(neighborhood)
            if borough == Borough.UNKNOWN:
                neighborhood, borough = extract_neighborhood(location_text)
        else:
            neighborhood, borough = extract_neighborhood(title)

        # Detect listing type from title
        listing_type = detect_listing_type(title)
        apartment_details = extract_apartment_details(title)
        is_furnished = extract_furnished(title)

        # Extract dates from title
        available_from, available_to = extract_date_range(title)

        return Listing(
            source=ListingSource.CRAIGSLIST,
            source_url=source_url,
            title=title,
            price_monthly=price,
            price_raw=price_text,
            neighborhood=neighborhood,
            borough=borough,
            listing_type=listing_type,
            apartment_details=apartment_details,
            is_furnished=is_furnished,
            available_from=available_from,
            available_to=available_to,
            description=title[:300],
            raw_text=title,
        )
