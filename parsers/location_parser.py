"""Neighborhood extraction and normalization from listing text."""

import re

from config.neighborhoods import (
    NEIGHBORHOOD_ALIASES,
    NEIGHBORHOOD_BOROUGHS,
    get_borough,
    normalize_neighborhood,
)
from models.enums import Borough


def extract_neighborhood(text: str) -> tuple[str, Borough]:
    """Extract and normalize a neighborhood from text.

    Returns (neighborhood_name, borough).
    Checks for known neighborhood names/aliases in the text.
    """
    if not text:
        return "", Borough.UNKNOWN

    lower = text.lower().strip()

    # First, check for exact alias matches (longest first for specificity)
    sorted_aliases = sorted(NEIGHBORHOOD_ALIASES.keys(), key=len, reverse=True)
    for alias in sorted_aliases:
        # Word boundary check to avoid partial matches
        pattern = r"(?:^|[\s,./\-()])" + re.escape(alias) + r"(?:$|[\s,./\-()])"
        if re.search(pattern, lower):
            canonical = NEIGHBORHOOD_ALIASES[alias]
            return canonical, get_borough(canonical)

    # Check for canonical neighborhood names directly
    sorted_names = sorted(NEIGHBORHOOD_BOROUGHS.keys(), key=len, reverse=True)
    for name in sorted_names:
        if name.lower() in lower:
            return name, get_borough(name)

    # Check for borough names as fallback
    borough_patterns = {
        Borough.MANHATTAN: [r"\bmanhattan\b", r"\bnyc\b"],
        Borough.BROOKLYN: [r"\bbrooklyn\b", r"\bbk\b"],
        Borough.QUEENS: [r"\bqueens\b"],
        Borough.BRONX: [r"\bbronx\b"],
    }
    for borough, patterns in borough_patterns.items():
        for pattern in patterns:
            if re.search(pattern, lower):
                return "", borough

    return "", Borough.UNKNOWN


def extract_neighborhood_from_parenthetical(text: str) -> str:
    """Extract neighborhood from Craigslist-style parenthetical: '(Midtown East)'."""
    match = re.search(r"\(([^)]+)\)\s*$", text)
    if match:
        return match.group(1).strip()
    return ""
