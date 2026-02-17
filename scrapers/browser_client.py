"""Playwright-based browser client for scraping Cloudflare-protected websites.

Replaces Firecrawl for LeaseBreak and Furnished Finder, which use Cloudflare
bot protection that blocks plain httpx requests. Uses a real browser to bypass
challenges, then converts HTML to markdown via html2text for LLM parsing.
"""

import logging
import time
from typing import Optional

import html2text
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Max seconds to wait for a Cloudflare challenge to resolve
CF_CHALLENGE_TIMEOUT = 15


class BrowserClient:
    """Playwright-based scraping client that bypasses Cloudflare protection.

    Usage:
        with BrowserClient() as client:
            html = client.fetch_html(url)
            markdown = client.fetch_markdown(url)
            results = client.batch_fetch_markdown(urls)
    """

    def __init__(self, delay_seconds: int = 2):
        self.delay_seconds = delay_seconds
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._last_request_time: float = 0

        # Configure html2text
        self._converter = html2text.HTML2Text()
        self._converter.ignore_images = True
        self._converter.body_width = 0  # No line wrapping
        self._converter.skip_internal_links = True
        self._converter.ignore_tables = False

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True, args=["--headless=new"]
        )
        self._context = self._browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
        )
        self._page = self._context.new_page()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _rate_limit(self):
        """Enforce delay between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        self._last_request_time = time.time()

    def _wait_for_cloudflare(self):
        """Wait for Cloudflare challenge to resolve."""
        for _ in range(CF_CHALLENGE_TIMEOUT):
            title = self._page.title().lower()
            if "just a moment" not in title and "attention required" not in title:
                return True
            self._page.wait_for_timeout(1000)
        logger.warning("Cloudflare challenge did not resolve in time")
        return False

    def fetch_html(self, url: str, timeout: float = 30.0) -> str:
        """Fetch a URL and return the HTML content.

        Args:
            url: The URL to fetch.
            timeout: Navigation timeout in seconds.

        Returns:
            The page HTML, or empty string on failure.
        """
        self._rate_limit()
        try:
            self._page.goto(url, timeout=timeout * 1000)
            self._wait_for_cloudflare()
            return self._page.content()
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return ""

    def fetch_markdown(self, url: str, timeout: float = 30.0) -> str:
        """Fetch a URL and return markdown-converted content.

        Args:
            url: The URL to fetch.
            timeout: Navigation timeout in seconds.

        Returns:
            Markdown string, or empty string on failure.
        """
        html = self.fetch_html(url, timeout=timeout)
        if not html:
            return ""
        return self._converter.handle(html)

    def batch_fetch_markdown(
        self, urls: list[str], timeout: float = 30.0
    ) -> dict[str, str]:
        """Fetch multiple URLs sequentially and return URL -> markdown mapping.

        Failed URLs are logged and skipped (fail-open).

        Args:
            urls: List of URLs to fetch.
            timeout: Per-page navigation timeout in seconds.

        Returns:
            Dict mapping URL to markdown content.
        """
        results = {}
        for i, url in enumerate(urls):
            try:
                markdown = self.fetch_markdown(url, timeout=timeout)
                if markdown:
                    results[url] = markdown
                if (i + 1) % 10 == 0:
                    logger.info(f"  Fetched {i + 1}/{len(urls)} pages")
            except Exception as e:
                logger.warning(f"  Failed to fetch {url}: {e}")
        return results
