"""Facebook Groups scraper — via Apify + Claude Haiku LLM parsing."""

import logging
from datetime import datetime
from typing import Optional

from apify_client import ApifyClient

from config.neighborhoods import get_borough, normalize_neighborhood
from models.enums import Borough, ListingSource, ListingType
from models.listing import Listing
from parsers.llm_parser import LLMParser
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

ACTOR_ID = "apify/facebook-groups-scraper"

# Map LLM output listing_type strings to our enums
TYPE_MAP = {
    "studio": ListingType.STUDIO,
    "1br": ListingType.ONE_BEDROOM,
    "2br": ListingType.TWO_BEDROOM,
    "3br+": ListingType.THREE_PLUS_BEDROOM,
    "room_in_shared": ListingType.ROOM_IN_SHARED,
    "hotel_extended_stay": ListingType.HOTEL_EXTENDED_STAY,
}

BOROUGH_MAP = {
    "manhattan": Borough.MANHATTAN,
    "brooklyn": Borough.BROOKLYN,
    "queens": Borough.QUEENS,
    "bronx": Borough.BRONX,
    "staten island": Borough.STATEN_ISLAND,
}


class FacebookGroupsScraper(BaseScraper):
    source_name = "Facebook Groups"

    def scrape(self) -> list[Listing]:
        if not self.settings.apify_api_token:
            logger.warning("No Apify API token configured, skipping Facebook Groups")
            return []

        if not self.settings.anthropic_api_key:
            logger.warning(
                "No Anthropic API key configured, skipping Facebook Groups "
                "(needed for LLM parsing)"
            )
            return []

        apify_client = ApifyClient(self.settings.apify_api_token)
        llm_parser = LLMParser(self.settings.anthropic_api_key)

        all_posts = []
        for group_url in self.settings.facebook_group_urls:
            try:
                posts = self._scrape_group(apify_client, group_url)
                all_posts.extend(posts)
            except Exception as e:
                logger.error(f"Failed to scrape FB group {group_url}: {e}")

        logger.info(f"Fetched {len(all_posts)} total Facebook posts")

        # Parse posts with LLM
        listings = []
        for post in all_posts:
            listing = self._parse_post(post, llm_parser)
            if listing:
                listings.append(listing)

        logger.info(f"Facebook Groups: {len(listings)} listings parsed")
        return listings

    def _scrape_group(self, client: ApifyClient, group_url: str) -> list[dict]:
        """Scrape a single Facebook group using Apify."""
        logger.info(f"Scraping Facebook group: {group_url}")

        run_input = {
            "startUrls": [{"url": group_url}],
            "maxPosts": 50,
            "maxComments": 0,
            "includeNestedComments": False,
        }

        run = client.actor(ACTOR_ID).call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        logger.info(f"  Got {len(items)} posts from {group_url}")
        return items

    def _parse_post(self, post: dict, llm_parser: LLMParser) -> Optional[Listing]:
        """Parse a single Facebook post into a Listing using the LLM."""
        # Extract the post text
        text = post.get("text", "") or post.get("message", "")
        if not text or len(text.strip()) < 20:
            return None

        # Get post URL
        post_url = post.get("url", "") or post.get("postUrl", "")

        # Get post timestamp
        posted_date = None
        timestamp = post.get("time", "") or post.get("timestamp", "")
        if timestamp:
            try:
                if isinstance(timestamp, str):
                    posted_date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                elif isinstance(timestamp, (int, float)):
                    posted_date = datetime.fromtimestamp(timestamp)
            except (ValueError, OSError):
                pass

        # Get images
        images = []
        if post.get("images"):
            images = post["images"] if isinstance(post["images"], list) else []
        elif post.get("media"):
            images = [m.get("url", "") for m in post.get("media", []) if m.get("url")]

        # Parse with LLM
        parsed = llm_parser.parse_facebook_post(text)
        if not parsed:
            return None

        # Skip "in search of" posts
        if parsed.get("is_iso"):
            return None

        # Map parsed fields to Listing
        neighborhood = ""
        borough = Borough.UNKNOWN
        if parsed.get("neighborhood"):
            neighborhood = normalize_neighborhood(parsed["neighborhood"])
            borough = get_borough(neighborhood)
        if borough == Borough.UNKNOWN and parsed.get("borough"):
            borough = BOROUGH_MAP.get(parsed["borough"].lower(), Borough.UNKNOWN)

        listing_type = ListingType.UNKNOWN
        if parsed.get("listing_type"):
            listing_type = TYPE_MAP.get(
                parsed["listing_type"].lower(), ListingType.UNKNOWN
            )

        # Parse dates
        available_from = None
        available_to = None
        if parsed.get("available_from"):
            try:
                from datetime import date as date_type
                parts = parsed["available_from"].split("-")
                available_from = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                pass
        if parsed.get("available_to"):
            try:
                from datetime import date as date_type
                parts = parsed["available_to"].split("-")
                available_to = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                pass

        return Listing(
            source=ListingSource.FACEBOOK,
            source_url=post_url,
            raw_text=text[:1000],
            title="",
            price_monthly=parsed.get("price_monthly"),
            price_raw=parsed.get("price_raw", ""),
            neighborhood=neighborhood,
            borough=borough,
            address=parsed.get("address", "") or "",
            listing_type=listing_type,
            apartment_details=parsed.get("apartment_details", "") or "",
            is_furnished=parsed.get("is_furnished"),
            available_from=available_from,
            available_to=available_to,
            posted_date=posted_date,
            description=parsed.get("description_summary", "") or "",
            contact_info=parsed.get("contact_info", "") or "",
            images=images,
        )
