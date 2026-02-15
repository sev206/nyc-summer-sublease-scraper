"""Craigslist NYC sublets scraper — RSS feed based."""

import logging
import re
import time
from datetime import datetime
from typing import Optional

import feedparser
import httpx
from bs4 import BeautifulSoup

from config.neighborhoods import get_borough, normalize_neighborhood
from models.enums import Borough, ListingSource, ListingType
from models.listing import Listing
from parsers.location_parser import (
    extract_neighborhood,
    extract_neighborhood_from_parenthetical,
)
from parsers.price_parser import extract_price_from_text, parse_price
from parsers.structured_parser import (
    detect_listing_type,
    extract_apartment_details,
    extract_furnished,
)
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

RSS_URL = "https://newyork.craigslist.org/search/sub?format=rss&max_price=2200"


class CraigslistScraper(BaseScraper):
    source_name = "Craigslist"

    def scrape(self) -> list[Listing]:
        logger.info(f"Fetching Craigslist RSS: {RSS_URL}")
        feed = feedparser.parse(RSS_URL)

        if not feed.entries:
            logger.warning("No entries found in Craigslist RSS feed")
            return []

        listings = []
        for entry in feed.entries[: self.settings.max_listings_per_source]:
            listing = self._parse_entry(entry)
            if listing:
                listings.append(listing)

        logger.info(f"Parsed {len(listings)} listings from Craigslist RSS")
        return listings

    def _parse_entry(self, entry: dict) -> Optional[Listing]:
        title = entry.get("title", "")
        link = entry.get("link", "")
        summary = entry.get("summary", "")
        published = entry.get("published", "")

        # Extract price from title (format: "Title - $1800 (Neighborhood)")
        price = self._extract_price_from_title(title)

        # Extract neighborhood from title parenthetical
        raw_neighborhood = extract_neighborhood_from_parenthetical(title)
        if raw_neighborhood:
            neighborhood = normalize_neighborhood(raw_neighborhood)
            borough = get_borough(neighborhood)
        else:
            neighborhood, borough = extract_neighborhood(title + " " + summary)

        # Detect listing type from title + summary
        listing_type = detect_listing_type(title + " " + summary)
        apartment_details = extract_apartment_details(title + " " + summary)
        is_furnished = extract_furnished(title + " " + summary)

        # Parse posted date
        posted_date = None
        if published:
            try:
                posted_date = datetime(*entry.published_parsed[:6])
            except (TypeError, AttributeError):
                pass

        # Clean title (remove price and neighborhood parenthetical)
        clean_title = re.sub(r"\s*-\s*\$[\d,]+.*$", "", title).strip()

        # Use summary as description, strip HTML
        description = ""
        if summary:
            soup = BeautifulSoup(summary, "html.parser")
            description = soup.get_text(separator=" ", strip=True)

        return Listing(
            source=ListingSource.CRAIGSLIST,
            source_url=link,
            title=clean_title,
            price_monthly=price,
            price_raw=self._extract_price_raw(title),
            neighborhood=neighborhood,
            borough=borough,
            listing_type=listing_type,
            apartment_details=apartment_details,
            is_furnished=is_furnished,
            posted_date=posted_date,
            description=description[:500],
            raw_text=title + " " + summary,
        )

    def _extract_price_from_title(self, title: str) -> Optional[int]:
        """Extract price from Craigslist title format: 'Title - $1800 (area)'."""
        match = re.search(r"\$(\d{1,2},?\d{3})", title)
        if match:
            return int(match.group(1).replace(",", ""))
        return extract_price_from_text(title)

    def _extract_price_raw(self, title: str) -> str:
        match = re.search(r"\$[\d,]+", title)
        return match.group(0) if match else ""
