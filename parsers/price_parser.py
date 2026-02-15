"""Price normalization utilities.

Handles formats like: $1800, $1,800, $1.8k, $450/week, $65/night, 1800/mo, etc.
Always returns monthly rent as an integer, or None if unparseable.
"""

import re
from typing import Optional


def parse_price(raw: str) -> Optional[int]:
    """Parse a raw price string into monthly rent (integer USD)."""
    if not raw:
        return None

    text = raw.lower().strip()

    # Remove common prefixes/noise
    text = text.replace(",", "").replace("$", "").strip()

    # Try "X.Xk" format (e.g., "1.8k" = 1800)
    k_match = re.search(r"(\d+\.?\d*)\s*k", text)
    if k_match:
        amount = float(k_match.group(1)) * 1000
        return _to_monthly(amount, text)

    # Try plain number
    num_match = re.search(r"(\d+\.?\d*)", text)
    if not num_match:
        return None

    amount = float(num_match.group(1))

    return _to_monthly(amount, text)


def _to_monthly(amount: float, text: str) -> Optional[int]:
    """Convert an amount to monthly based on context clues in the text."""
    text = text.lower()

    # Per night / nightly
    if any(w in text for w in ["/night", "per night", "/nite", "nightly", "/n"]):
        return int(amount * 30)

    # Per week / weekly
    if any(w in text for w in ["/week", "per week", "/wk", "weekly", "/w"]):
        return int(amount * 4.33)

    # Per year / annually (unlikely but handle it)
    if any(w in text for w in ["/year", "per year", "/yr", "annually"]):
        return int(amount / 12)

    # Already monthly (default) — sanity check
    monthly = int(amount)

    # If the number is suspiciously low, it might be weekly or nightly
    if monthly < 200:
        # Likely a nightly rate
        return int(monthly * 30)
    if monthly < 600:
        # Likely a weekly rate
        return int(monthly * 4.33)

    return monthly


def extract_price_from_text(text: str) -> Optional[int]:
    """Try to find and parse a price from a longer text block."""
    if not text:
        return None

    # Look for dollar sign patterns
    patterns = [
        r"\$[\d,]+\.?\d*\s*[kK]?\s*(?:/\s*(?:mo|month|week|wk|night|nite))?",
        r"[\d,]+\.?\d*\s*[kK]?\s*(?:/\s*(?:mo|month|week|wk|night|nite))",
        r"\$[\d,]+\.?\d*\s*[kK]?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            result = parse_price(match.group(0))
            if result and 100 <= result <= 15000:
                return result

    return None
