"""Facebook Groups scraper - via Apify + Claude Haiku LLM parsing."""

import logging
from datetime import datetime
from typing import Optional

from apify_client import ApifyClient

from models.enums import ListingSource
from models.listing import Listing
from parsers.llm_parser import LLMParser, listing_from_parsed
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

ACTOR_ID = "apify/facebook-groups-scraper"


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
            "resultsLimit": 10,
            "onlyPostsNewerThan": "5 hours",
            "maxComments": 0,
            "includeNestedComments": False,
        }

        run = client.actor(ACTOR_ID).call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        count = len(items)
        limit = run_input["resultsLimit"]
        logger.info(f"  Got {count} posts from {group_url}")
        if count >= limit:
            logger.warning(
                f"  HIT LIMIT: {group_url} returned {count}/{limit} "
                f"posts — likely missed some. Consider increasing resultsLimit or frequency."
            )
            if self.sheet_sync:
                self.sheet_sync.log_hit_limit("Facebook Groups", group_url, count, limit)
        return items

    def _parse_post(self, post: dict, llm_parser: LLMParser) -> Optional[Listing]:
        """Parse a single Facebook post into a Listing using the LLM."""
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

        # Use shared helper to create listing
        listing = listing_from_parsed(parsed, ListingSource.FACEBOOK)

        # Override with post-level metadata
        listing.source_url = post_url
        listing.raw_text = text[:1000]
        listing.posted_date = posted_date
        listing.images = images

        return listing
