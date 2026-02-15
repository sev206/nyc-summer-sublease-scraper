from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(UTC)

from pydantic import BaseModel, Field

from models.enums import Borough, ListingSource, ListingType


class Listing(BaseModel):
    # Identity
    id: str = ""
    source: ListingSource
    source_url: str = ""
    raw_text: str = ""

    # Core fields
    title: str = ""
    price_monthly: Optional[int] = None
    price_raw: str = ""

    # Location
    neighborhood: str = ""
    borough: Borough = Borough.UNKNOWN
    address: str = ""

    # Type
    listing_type: ListingType = ListingType.UNKNOWN
    apartment_details: str = ""  # e.g. "3b2ba"
    is_furnished: Optional[bool] = None

    # Availability
    available_from: Optional[date] = None
    available_to: Optional[date] = None

    # Scoring (populated by rating engine)
    rating: float = 0.0
    rating_breakdown: dict = Field(default_factory=dict)

    # Metadata
    posted_date: Optional[datetime] = None
    scraped_at: datetime = Field(default_factory=_utcnow)
    description: str = ""
    contact_info: str = ""
    images: list[str] = Field(default_factory=list)

    def generate_fingerprint(self) -> str:
        """Create a dedup fingerprint from core listing attributes."""
        # For structured sites, URL is the stable identifier
        if self.source != ListingSource.FACEBOOK and self.source_url:
            content = self.source_url
        else:
            # Content-based fingerprint for Facebook posts
            normalized_text = " ".join(self.raw_text.lower().split()[:50])
            content = f"{self.price_monthly}|{self.neighborhood.lower()}|{self.listing_type}|{normalized_text}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_sheet_row(self) -> list:
        """Convert to a row for Google Sheets."""
        breakdown = self.rating_breakdown
        breakdown_str = " ".join(
            f"{k[0].upper()}:{v}" for k, v in breakdown.items()
        ) if breakdown else ""

        return [
            "New",                                          # A: Status
            self.rating,                                    # B: Rating
            self.price_monthly if self.price_monthly else "N/A",  # C: Price
            self.neighborhood,                              # D: Neighborhood
            self.borough.value,                             # E: Borough
            self.listing_type.value,                        # F: Type
            self.apartment_details,                         # G: Apartment Details
            str(self.available_from) if self.available_from else "",  # H: Available From
            str(self.available_to) if self.available_to else "",     # I: Available To
            "Yes" if self.is_furnished else ("No" if self.is_furnished is False else ""),  # J: Furnished
            self.source.value,                              # K: Source
            self.source_url,                                # L: Link
            self.description[:300],                         # M: Description
            breakdown_str,                                  # N: Rating Breakdown
            self.contact_info,                              # O: Contact
            self.scraped_at.isoformat(),                    # P: Scraped At
            self.id,                                        # Q: Listing ID
        ]
