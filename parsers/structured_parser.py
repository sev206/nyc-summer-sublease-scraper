"""Rule-based parser for structured listing sites (Craigslist, etc.)."""

import re
from typing import Optional

from models.enums import ListingType


def detect_listing_type(text: str) -> ListingType:
    """Detect listing type from text content."""
    lower = text.lower()

    # Studio indicators
    if any(w in lower for w in ["studio", "alcove studio", "bachelor"]):
        return ListingType.STUDIO

    # Bedroom count patterns
    br_patterns = [
        (r"\b1\s*(?:br|bed|bedroom|bdrm)\b", ListingType.ONE_BEDROOM),
        (r"\bone\s*(?:br|bed|bedroom|bdrm)\b", ListingType.ONE_BEDROOM),
        (r"\b2\s*(?:br|bed|bedroom|bdrm)\b", ListingType.TWO_BEDROOM),
        (r"\btwo\s*(?:br|bed|bedroom|bdrm)\b", ListingType.TWO_BEDROOM),
        (r"\b[3-9]\s*(?:br|bed|bedroom|bdrm)\b", ListingType.THREE_PLUS_BEDROOM),
    ]
    for pattern, listing_type in br_patterns:
        if re.search(pattern, lower):
            return listing_type

    # Hotel / extended stay
    if any(w in lower for w in ["hotel", "extended stay", "suite", "apart-hotel"]):
        return ListingType.HOTEL_EXTENDED_STAY

    # Room in shared apartment
    room_indicators = [
        "room for rent", "room available", "shared apartment",
        "private room", "room in", "roommate", "looking for roommate",
        "spare room", "furnished room", "one room",
    ]
    if any(w in lower for w in room_indicators):
        return ListingType.ROOM_IN_SHARED

    return ListingType.UNKNOWN


def extract_apartment_details(text: str) -> str:
    """Extract apartment details like '3b2ba' from text."""
    lower = text.lower()

    # Pattern: "3 bed 2 bath" / "3br/2ba" / "3b2b" etc.
    pattern = re.search(
        r"(\d)\s*(?:bed(?:room)?s?|br|b)\s*[/,]?\s*(\d)\s*(?:bath(?:room)?s?|ba|b)",
        lower,
    )
    if pattern:
        return f"{pattern.group(1)}b{pattern.group(2)}ba"

    # Just bedrooms
    br_match = re.search(r"(\d)\s*(?:bed(?:room)?s?|br)", lower)
    if br_match:
        return f"{br_match.group(1)}br"

    if "studio" in lower:
        return "Studio"

    return ""


def extract_furnished(text: str) -> Optional[bool]:
    """Detect if listing mentions furnished/unfurnished."""
    lower = text.lower()
    if "unfurnished" in lower or "un-furnished" in lower:
        return False
    if "furnished" in lower:
        return True
    return None
