"""Listings Project scraper - curated weekly listings.

The correct URL is /real-estate/new-york-city/sublets (not /listings which
shows only navigation). The page has rich listing data including price, dates,
neighborhood, and description.
"""

import logging

from models.enums import ListingSource
from models.listing import Listing
from parsers.llm_parser import LLMParser, listing_from_parsed
from scrapers.base import BaseScraper
from scrapers.firecrawl_client import FirecrawlClient, FirecrawlCreditError

logger = logging.getLogger(__name__)

LISTINGS_PROJECT_URLS = [
    "https://www.listingsproject.com/real-estate/new-york-city/sublets",
    "https://www.listingsproject.com/real-estate/new-york-city/rentals",
]


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

        for url in LISTINGS_PROJECT_URLS:
            try:
                logger.info(f"Scraping Listings Project: {url}")
                markdown = client.scrape_markdown(url, timeout=90.0)
                logger.info(f"  Got {len(markdown)} chars of markdown")
                parsed_listings = llm_parser.parse_listings_page(
                    markdown, "Listings Project NYC Apartments", max_chars=25000
                )
                for parsed in parsed_listings:
                    listing = listing_from_parsed(
                        parsed, ListingSource.LISTINGS_PROJECT
                    )
                    listings.append(listing)
            except FirecrawlCreditError:
                logger.error("Firecrawl credits exhausted, stopping Listings Project")
                break
            except Exception as e:
                logger.error(f"Failed to scrape Listings Project {url}: {e}")

        logger.info(f"Listings Project: {len(listings)} listings scraped")
        return listings
