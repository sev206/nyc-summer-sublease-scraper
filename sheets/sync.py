"""Google Sheets sync — append new listings, preserve user Status column."""

import logging
from datetime import datetime
from typing import Optional

import gspread

from models.listing import Listing
from sheets.client import (
    ensure_fb_state_worksheet,
    ensure_headers,
    ensure_log_worksheet,
    ensure_seen_worksheet,
)

logger = logging.getLogger(__name__)


class SheetSync:
    def __init__(self, spreadsheet: gspread.Spreadsheet):
        self.spreadsheet = spreadsheet

        # Main listings worksheet
        self.worksheet = spreadsheet.sheet1
        ensure_headers(self.worksheet)

        # Dedup persistence worksheet
        self.seen_ws = ensure_seen_worksheet(spreadsheet)

        # Monitoring log worksheet
        self.log_ws = ensure_log_worksheet(spreadsheet)

        # Facebook scrape state worksheet
        self.fb_state_ws = ensure_fb_state_worksheet(spreadsheet)

    def get_existing_ids(self) -> set[str]:
        """Read the Listing ID column to get all existing fingerprints."""
        try:
            col_values = self.worksheet.col_values(17)  # Column Q = Listing ID
            return set(col_values[1:])  # Skip header
        except Exception:
            return set()

    def get_existing_source_urls(self) -> set[str]:
        """Read the Link column (L) to get all previously scraped URLs."""
        try:
            col_values = self.worksheet.col_values(12)  # Column L = Link
            return {v for v in col_values[1:] if v}  # Skip header, skip blanks
        except Exception:
            return set()

    def get_seen_fingerprints(self) -> set[str]:
        """Read all fingerprints from the _seen worksheet."""
        try:
            col_values = self.seen_ws.col_values(1)
            return set(col_values[1:])  # Skip header
        except Exception:
            return set()

    def mark_seen(self, fingerprint: str, source: str) -> None:
        """Add a fingerprint to the _seen worksheet."""
        now = datetime.utcnow().isoformat()
        self.seen_ws.append_row(
            [fingerprint, source, now],
            value_input_option="USER_ENTERED",
        )

    def mark_seen_batch(self, entries: list[tuple[str, str]]) -> None:
        """Batch-add fingerprints to the _seen worksheet."""
        if not entries:
            return
        now = datetime.utcnow().isoformat()
        rows = [[fp, source, now] for fp, source in entries]
        self.seen_ws.append_rows(rows, value_input_option="USER_ENTERED")

    def log_hit_limit(self, source: str, group_url: str, count: int, limit: int) -> None:
        """Log a hit-limit event to the _log worksheet."""
        try:
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            self.log_ws.append_row(
                [now, source, group_url, count, limit],
                value_input_option="USER_ENTERED",
            )
        except Exception as e:
            logger.warning(f"Failed to write hit-limit log: {e}")

    def get_fb_last_scrape(self, group_url: str) -> Optional[datetime]:
        """Get the last scrape timestamp for a Facebook group."""
        try:
            urls = self.fb_state_ws.col_values(1)
            for i, url in enumerate(urls):
                if url == group_url:
                    timestamp_str = self.fb_state_ws.cell(i + 1, 2).value
                    if timestamp_str:
                        return datetime.fromisoformat(timestamp_str)
            return None
        except Exception as e:
            logger.warning(f"Failed to read FB state for {group_url}: {e}")
            return None

    def set_fb_last_scrape(self, group_url: str) -> None:
        """Record the current time as last scrape for a Facebook group."""
        now = datetime.utcnow().isoformat()
        try:
            urls = self.fb_state_ws.col_values(1)
            for i, url in enumerate(urls):
                if url == group_url:
                    self.fb_state_ws.update_cell(i + 1, 2, now)
                    return
            # Not found — append new row
            self.fb_state_ws.append_row(
                [group_url, now], value_input_option="USER_ENTERED"
            )
        except Exception as e:
            logger.warning(f"Failed to write FB state for {group_url}: {e}")

    def append_listings(self, listings: list[Listing]) -> int:
        """Append new listings to the sheet. Returns count of rows added.

        Only appends listings whose ID is not already in the sheet.
        New listings are sorted by rating (highest first).
        The Status column (A) of existing rows is never touched.
        """
        existing_ids = self.get_existing_ids()

        new_listings = [l for l in listings if l.id and l.id not in existing_ids]
        if not new_listings:
            logger.info("No new listings to add")
            return 0

        # Sort by rating descending
        new_listings.sort(key=lambda l: l.rating, reverse=True)

        rows = [l.to_sheet_row() for l in new_listings]
        self.worksheet.append_rows(rows, value_input_option="USER_ENTERED")

        # Mark all as seen
        seen_entries = [(l.id, l.source.value) for l in new_listings]
        self.mark_seen_batch(seen_entries)

        # Re-sort the entire sheet by Rating (column B) descending
        self._sort_by_rating()

        logger.info(f"Added {len(rows)} new listings to sheet")
        return len(rows)

    def _sort_by_rating(self) -> None:
        """Sort all data rows by Rating (column B) descending."""
        try:
            row_count = len(self.worksheet.col_values(1))
            if row_count <= 1:
                return  # Only header, nothing to sort
            # Sort range A2:Q{last_row} by column 2 (Rating) descending
            self.worksheet.sort(
                (2, "des"), range=f"A2:Q{row_count}"
            )
            logger.info(f"Sorted {row_count - 1} rows by rating")
        except Exception as e:
            logger.warning(f"Failed to sort sheet by rating: {e}")
