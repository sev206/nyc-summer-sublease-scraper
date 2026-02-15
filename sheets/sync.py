"""Google Sheets sync — append new listings, preserve user Status column."""

import logging
from datetime import datetime

import gspread

from models.listing import Listing
from sheets.client import ensure_headers, ensure_seen_worksheet

logger = logging.getLogger(__name__)


class SheetSync:
    def __init__(self, spreadsheet: gspread.Spreadsheet):
        self.spreadsheet = spreadsheet

        # Main listings worksheet
        self.worksheet = spreadsheet.sheet1
        ensure_headers(self.worksheet)

        # Dedup persistence worksheet
        self.seen_ws = ensure_seen_worksheet(spreadsheet)

    def get_existing_ids(self) -> set[str]:
        """Read the Listing ID column to get all existing fingerprints."""
        try:
            col_values = self.worksheet.col_values(17)  # Column Q = Listing ID
            return set(col_values[1:])  # Skip header
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

        logger.info(f"Added {len(rows)} new listings to sheet")
        return len(rows)
