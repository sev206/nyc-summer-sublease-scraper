"""Firecrawl REST API client for scraping websites."""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

FIRECRAWL_BASE_URL = "https://api.firecrawl.dev/v1"


class FirecrawlClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def scrape(
        self,
        url: str,
        formats: Optional[list[str]] = None,
        timeout: float = 60.0,
    ) -> dict:
        """Scrape a single URL and return the response.

        Args:
            url: The URL to scrape.
            formats: Output formats, e.g. ["markdown"], ["html"], ["markdown", "html"].
            timeout: Request timeout in seconds.

        Returns:
            The Firecrawl API response dict with 'data' containing the scraped content.
        """
        if formats is None:
            formats = ["markdown"]

        payload = {
            "url": url,
            "formats": formats,
        }

        try:
            response = httpx.post(
                f"{FIRECRAWL_BASE_URL}/scrape",
                headers=self.headers,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Firecrawl HTTP error for {url}: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Firecrawl request error for {url}: {e}")
            raise

    def scrape_markdown(self, url: str, timeout: float = 60.0) -> str:
        """Scrape a URL and return just the markdown content."""
        result = self.scrape(url, formats=["markdown"], timeout=timeout)
        data = result.get("data", {})
        return data.get("markdown", "")
