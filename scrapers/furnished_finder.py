"""Furnished Finder scraper - furnished short-term rentals.

Furnished Finder's search page uses lazy loading so only ~6 listings render
per page. We scrape multiple paginated search pages to collect property URLs
using BeautifulSoup, then fetch individual listing pages via Playwright and
parse each with the LLM.
"""

import logging
import re

from bs4 import BeautifulSoup

from models.enums import ListingSource
from models.listing import Listing
from parsers.llm_parser import LLMParser, listing_from_parsed
from scrapers.base import BaseScraper
from scrapers.browser_client import BrowserClient

logger = logging.getLogger(__name__)

# Borough-specific search URLs with date and price filters
FURNISHED_FINDER_URLS = [
    (
        "https://www.furnishedfinder.com/housing/us--ny--manhattan"
        "?max-price=2300&move-in-date=2026-07-01&move-out-date=2026-09-30"
    ),
    (
        "https://www.furnishedfinder.com/housing/us--ny--brooklyn"
        "?max-price=2300&move-in-date=2026-07-01&move-out-date=2026-09-30"
    ),
    (
        "https://www.furnishedfinder.com/housing/us--ny--queens"
        "?max-price=2300&move-in-date=2026-07-01&move-out-date=2026-09-30"
    ),
]

# Number of search pages to scrape per borough (lazy loading yields ~6-36 per page)
MAX_SEARCH_PAGES = 3

# Max individual listing pages to batch-scrape per borough
MAX_LISTINGS_PER_BOROUGH = 50

# Matches property IDs from URLs like /property/963105_1
PROPERTY_URL_PATTERN = re.compile(r"/property/(\d+)_\d+")


class FurnishedFinderScraper(BaseScraper):
    source_name = "Furnished Finder"

    def scrape(self) -> list[Listing]:
        if not self.settings.anthropic_api_key:
            logger.warning("No Anthropic API key, skipping Furnished Finder")
            return []

        llm_parser = LLMParser(self.settings.anthropic_api_key)
        listings = []

        with BrowserClient(delay_seconds=self.settings.scrape_delay_seconds) as client:
            for search_url in FURNISHED_FINDER_URLS:
                try:
                    borough_listings = self._scrape_borough(
                        client, llm_parser, search_url
                    )
                    listings.extend(borough_listings)
                except Exception as e:
                    logger.error(
                        f"Failed to scrape Furnished Finder {search_url}: {e}"
                    )

        logger.info(f"Furnished Finder: {len(listings)} listings scraped")
        return listings

    def _scrape_borough(
        self,
        client: BrowserClient,
        llm_parser: LLMParser,
        search_url: str,
    ) -> list[Listing]:
        """Scrape one borough: paginate search pages, extract URLs, fetch details."""
        logger.info(f"Scraping Furnished Finder search: {search_url}")

        # Step 1: Scrape multiple search pages to collect property URLs
        seen_ids: set[str] = set()
        for page_num in range(1, MAX_SEARCH_PAGES + 1):
            page_url = (
                f"{search_url}&page={page_num}" if page_num > 1 else search_url
            )
            try:
                html = client.fetch_html(page_url, timeout=60.0)
                if not html:
                    logger.warning(f"  Empty response from page {page_num}")
                    continue

                soup = BeautifulSoup(html, "html.parser")
                links = soup.select('a[href*="/property/"]')
                new_ids: set[str] = set()
                for link in links:
                    m = PROPERTY_URL_PATTERN.search(link.get("href", ""))
                    if m:
                        new_ids.add(m.group(1))

                before = len(seen_ids)
                seen_ids.update(new_ids)
                added = len(seen_ids) - before
                logger.info(
                    f"  Page {page_num}: found {len(new_ids)} IDs, "
                    f"{added} new (total {len(seen_ids)})"
                )
                # Stop paginating if this page added nothing new
                if added == 0:
                    break
                # Stop paginating if all found IDs are already known
                if self.known_urls and new_ids:
                    new_urls = {
                        f"https://www.furnishedfinder.com/property/{pid}_1"
                        for pid in new_ids
                    }
                    if new_urls.issubset(self.known_urls):
                        logger.info(
                            "  All IDs on this page already known, "
                            "stopping pagination"
                        )
                        break
            except Exception as e:
                logger.warning(f"  Failed to scrape search page {page_num}: {e}")

        logger.info(f"  Found {len(seen_ids)} unique property IDs")

        if not seen_ids:
            return []

        # Step 2: Sort by property ID descending (newest first), take top N
        sorted_ids = sorted(seen_ids, key=int, reverse=True)
        top_ids = sorted_ids[:MAX_LISTINGS_PER_BOROUGH]
        urls_to_scrape = [
            f"https://www.furnishedfinder.com/property/{pid}_1"
            for pid in top_ids
        ]

        # Filter out URLs we've already scraped in previous runs
        if self.known_urls:
            before = len(urls_to_scrape)
            urls_to_scrape = [
                u for u in urls_to_scrape if u not in self.known_urls
            ]
            skipped = before - len(urls_to_scrape)
            if skipped:
                logger.info(f"  Skipped {skipped} already-known URLs")

        if not urls_to_scrape:
            logger.info("  All listings already known, nothing to scrape")
            return []

        logger.info(f"  Fetching {len(urls_to_scrape)} new listings")

        # Step 3: Fetch individual listing pages via Playwright
        url_to_markdown = client.batch_fetch_markdown(
            urls_to_scrape, timeout=30.0
        )
        logger.info(f"  Got {len(url_to_markdown)} page results")

        # Step 4: Parse each page with LLM
        listings = []
        for url, markdown in url_to_markdown.items():
            try:
                parsed_list = llm_parser.parse_listings_page(
                    markdown, "Furnished Finder NYC Rental", max_chars=6000
                )
                for parsed in parsed_list:
                    listing = listing_from_parsed(
                        parsed,
                        ListingSource.FURNISHED_FINDER,
                        default_furnished=True,
                    )
                    if not listing.source_url or listing.source_url == "":
                        listing.source_url = url
                    listings.append(listing)
            except Exception as e:
                logger.warning(
                    f"  Failed to parse Furnished Finder page {url}: {e}"
                )

        return listings
