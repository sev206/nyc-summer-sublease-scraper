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

    def batch_scrape(
        self,
        urls: list[str],
        formats: list[str] | None = None,
        timeout: float = 300.0,
        poll_interval: float = 5.0,
    ) -> list[dict]:
        """Batch scrape multiple URLs. Returns list of result dicts.

        Uses Firecrawl's async batch endpoint, polling until complete.
        """
        import time

        if formats is None:
            formats = ["markdown"]

        if not urls:
            return []

        payload = {"urls": urls, "formats": formats}

        try:
            # Start batch job
            response = httpx.post(
                f"{FIRECRAWL_BASE_URL}/batch/scrape",
                headers=self.headers,
                json=payload,
                timeout=60.0,
            )
            response.raise_for_status()
            batch_data = response.json()
            batch_id = batch_data.get("id")
            if not batch_id:
                logger.error("Firecrawl batch: no batch ID returned")
                return []

            logger.info(f"Firecrawl batch started: {batch_id} ({len(urls)} URLs)")

            # Poll until done
            deadline = time.time() + timeout
            while time.time() < deadline:
                time.sleep(poll_interval)
                status_resp = httpx.get(
                    f"{FIRECRAWL_BASE_URL}/batch/scrape/{batch_id}",
                    headers=self.headers,
                    timeout=30.0,
                )
                status_resp.raise_for_status()
                status_data = status_resp.json()

                status = status_data.get("status", "")
                if status == "completed":
                    results = status_data.get("data", [])
                    logger.info(f"Firecrawl batch complete: {len(results)} results")
                    return results
                elif status == "failed":
                    logger.error("Firecrawl batch job failed")
                    return []

            logger.warning("Firecrawl batch timed out")
            return []

        except httpx.HTTPStatusError as e:
            logger.error(f"Firecrawl batch HTTP error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Firecrawl batch error: {e}")
            return []

    def batch_scrape_markdown(
        self, urls: list[str], timeout: float = 300.0
    ) -> dict[str, str]:
        """Batch scrape URLs and return a URL -> markdown mapping."""
        results = self.batch_scrape(urls, formats=["markdown"], timeout=timeout)
        output = {}
        for item in results:
            md = item.get("markdown", "")
            source_url = item.get("metadata", {}).get("sourceURL", "")
            if source_url and md:
                output[source_url] = md
        return output
