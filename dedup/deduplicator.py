"""Deduplication engine — fingerprint-based with Google Sheet persistence."""

import logging
from typing import Optional

from thefuzz import fuzz

from models.listing import Listing

logger = logging.getLogger(__name__)


class Deduplicator:
    def __init__(self, sheet_sync: Optional["SheetSync"] = None):
        """Initialize with optional SheetSync for persistence.

        If sheet_sync is None (dry-run mode), only in-memory dedup is performed.
        """
        self.sheet_sync = sheet_sync
        self._seen_fingerprints: set[str] = set()

        # Load previously seen fingerprints from sheet
        if sheet_sync:
            self._seen_fingerprints = sheet_sync.get_seen_fingerprints()
            sheet_ids = sheet_sync.get_existing_ids()
            self._seen_fingerprints.update(sheet_ids)
            logger.info(
                f"Loaded {len(self._seen_fingerprints)} previously seen fingerprints"
            )

    def deduplicate(self, listings: list[Listing]) -> list[Listing]:
        """Remove duplicates from a batch of listings.

        1. Check each listing's fingerprint against the seen set
        2. Check for fuzzy duplicates within the current batch
        3. Return only new, unique listings
        """
        new_listings: list[Listing] = []
        batch_fingerprints: set[str] = set()

        for listing in listings:
            fp = listing.id or listing.generate_fingerprint()
            listing.id = fp

            # Skip if already seen (from sheet or previous runs)
            if fp in self._seen_fingerprints:
                continue

            # Skip if duplicate within this batch
            if fp in batch_fingerprints:
                continue

            # Fuzzy cross-source duplicate check against new listings
            if self._is_fuzzy_duplicate(listing, new_listings):
                continue

            batch_fingerprints.add(fp)
            new_listings.append(listing)

        logger.info(
            f"Dedup: {len(listings)} input -> {len(new_listings)} unique new listings"
        )
        return new_listings

    def _is_fuzzy_duplicate(self, candidate: Listing, existing: list[Listing]) -> bool:
        """Check if a listing is a fuzzy duplicate of any existing listing."""
        for other in existing:
            if self._are_likely_duplicates(candidate, other):
                return True
        return False

    @staticmethod
    def _are_likely_duplicates(a: Listing, b: Listing) -> bool:
        """Two listings are likely duplicates if they match on multiple signals."""
        # Same price (within $50)
        if a.price_monthly and b.price_monthly:
            if abs(a.price_monthly - b.price_monthly) > 50:
                return False
        elif a.price_monthly != b.price_monthly:
            return False

        # Same neighborhood
        if a.neighborhood and b.neighborhood:
            if a.neighborhood.lower() != b.neighborhood.lower():
                return False

        # Same type
        if a.listing_type != b.listing_type:
            return False

        # Text similarity check
        text_a = (a.description or a.raw_text)[:200]
        text_b = (b.description or b.raw_text)[:200]
        if text_a and text_b:
            similarity = fuzz.token_sort_ratio(text_a, text_b)
            return similarity > 70

        return False
