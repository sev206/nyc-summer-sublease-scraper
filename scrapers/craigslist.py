"""Craigslist NYC sublets scraper - with individual page scraping for accurate data."""

import logging
import re
import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config.neighborhoods import get_borough, normalize_neighborhood
from models.enums import Borough, ListingSource, ListingType
from models.listing import Listing
from parsers.date_parser import extract_date_range, parse_date
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

        # Skip already-known URLs
        if source_url in self.known_urls:
            return None

        # Extract title
        title_el = item.select_one(".title")
        title = title_el.get_text(strip=True) if title_el else ""

        # Extract basic price from search result
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

        # Extract dates from title (fallback)
        available_from, available_to = extract_date_range(title)
        description = title[:300]
        raw_text = title

        # Fetch individual listing page for accurate price, dates, and attributes
        details = self._fetch_listing_details(source_url)
        if details:
            # Use rent_period to correctly compute monthly price
            rent_period = details.get("rent_period")
            if rent_period and rent_period != "monthly":
                price = _adjust_price_for_period(price, rent_period)

            # Use individual page dates if we didn't get them from the title
            if details.get("available_from") and not available_from:
                available_from = details["available_from"]
            if details.get("available_to") and not available_to:
                available_to = details["available_to"]

            # Override with individual page attributes
            if details.get("is_furnished") is not None:
                is_furnished = details["is_furnished"]
            if details.get("apartment_details"):
                apartment_details = details["apartment_details"]
            if details.get("description"):
                description = details["description"][:300]
                raw_text = details["description"]
            if details.get("address"):
                # Try to get better neighborhood from address
                addr_neighborhood, addr_borough = extract_neighborhood(
                    details["address"]
                )
                if addr_borough != Borough.UNKNOWN and borough == Borough.UNKNOWN:
                    neighborhood = addr_neighborhood
                    borough = addr_borough

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
            description=description,
            raw_text=raw_text,
        )

    def _fetch_listing_details(self, url: str) -> Optional[dict]:
        """Fetch a Craigslist individual listing page and parse details."""
        try:
            time.sleep(self.settings.scrape_delay_seconds)
            response = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=30.0,
                follow_redirects=True,
            )
            response.raise_for_status()
            return parse_craigslist_listing_page(response.text)
        except Exception as e:
            logger.warning(f"Failed to fetch listing details from {url}: {e}")
            return None


def parse_craigslist_listing_page(html: str) -> dict:
    """Parse a Craigslist individual listing page for detailed info.

    Extracts: rent_period, available_from, available_to, is_furnished,
    apartment_details, description, address.
    """
    soup = BeautifulSoup(html, "html.parser")
    details: dict = {}

    # Extract rent period from .attrgroup .rent_period
    rent_period_div = soup.select_one(".attrgroup .rent_period")
    if rent_period_div:
        link = rent_period_div.select_one(".valu a")
        if link:
            period_text = link.get_text(strip=True).lower()
            if "week" in period_text:
                details["rent_period"] = "weekly"
            elif "daily" in period_text or "day" in period_text:
                details["rent_period"] = "daily"
            else:
                details["rent_period"] = "monthly"

    # Extract available date and apartment details from first .attrgroup
    attrgroups = soup.select(".attrgroup")
    if attrgroups:
        first_group = attrgroups[0]
        for span in first_group.select("span.attr"):
            text = span.get_text(strip=True).lower()
            if text.startswith("available"):
                date_text = text.replace("available", "").strip()
                details["available_from"] = parse_date(date_text)
            elif re.search(r"\d+br|\d+ba", text, re.IGNORECASE):
                details["apartment_details"] = span.get_text(strip=True)

    # Extract attributes (furnished, etc.) from the last .attrgroup
    if len(attrgroups) >= 3:
        attrs_group = attrgroups[2]
        for link in attrs_group.select("a"):
            href = link.get("href", "")
            if "is_furnished=1" in href:
                details["is_furnished"] = True

    # Extract description from #postingbody
    posting_body = soup.select_one("#postingbody")
    if posting_body:
        # Remove the QR code / print info elements
        for el in posting_body.select(".print-information"):
            el.decompose()
        desc = posting_body.get_text(separator=" ", strip=True)
        details["description"] = desc

        # Try to extract dates from description too
        if "available_from" not in details:
            avail_from, avail_to = extract_date_range(desc)
            if avail_from:
                details["available_from"] = avail_from
            if avail_to:
                details["available_to"] = avail_to

    # Extract address from h2.street-address
    address_el = soup.select_one("h2.street-address")
    if address_el:
        details["address"] = address_el.get_text(strip=True)

    return details


MAX_REASONABLE_MONTHLY = 5000


def _adjust_price_for_period(
    price: Optional[int], rent_period: str
) -> Optional[int]:
    """Adjust a price to monthly based on the explicit rent period.

    If the converted monthly price exceeds MAX_REASONABLE_MONTHLY, the
    rent_period is likely set incorrectly by the poster, so the original
    price is returned as-is (assumed monthly).
    """
    if price is None:
        return None
    if rent_period == "weekly":
        adjusted = int(price * 4.33)
    elif rent_period == "daily":
        adjusted = int(price * 30)
    else:
        return price

    if adjusted > MAX_REASONABLE_MONTHLY:
        return price
    return adjusted
