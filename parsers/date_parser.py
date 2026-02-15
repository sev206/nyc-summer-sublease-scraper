"""Date range normalization utilities.

Parses various date formats from listing text into Python date objects.
"""

import re
from datetime import date
from typing import Optional


# Month name/abbreviation → number
MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def parse_date(raw: str, default_year: int = 2026) -> Optional[date]:
    """Parse a single date string into a date object.

    Supports:
      - "July 1" / "Jul 1" / "7/1" / "07/01" / "2026-07-01"
      - "July 1st" / "August 15th"
    """
    if not raw:
        return None

    text = raw.strip().lower()
    # Remove ordinal suffixes
    text = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text)

    # ISO format: 2026-07-01
    iso_match = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if iso_match:
        return date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))

    # US format: MM/DD or MM/DD/YYYY
    us_match = re.match(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", text)
    if us_match:
        month = int(us_match.group(1))
        day = int(us_match.group(2))
        year_str = us_match.group(3)
        if year_str:
            year = int(year_str)
            if year < 100:
                year += 2000
        else:
            year = default_year
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                return date(year, month, day)
            except ValueError:
                return None

    # Month name + day: "July 1" / "Jul 1"
    name_match = re.match(r"([a-z]+)\s+(\d{1,2})", text)
    if name_match:
        month_name = name_match.group(1)
        day = int(name_match.group(2))
        month = MONTH_MAP.get(month_name)
        if month and 1 <= day <= 31:
            try:
                return date(default_year, month, day)
            except ValueError:
                return None

    # Day + month name: "1 July" / "1st of July"
    day_name_match = re.match(r"(\d{1,2})\s+(?:of\s+)?([a-z]+)", text)
    if day_name_match:
        day = int(day_name_match.group(1))
        month_name = day_name_match.group(2)
        month = MONTH_MAP.get(month_name)
        if month and 1 <= day <= 31:
            try:
                return date(default_year, month, day)
            except ValueError:
                return None

    return None


def extract_date_range(text: str) -> tuple[Optional[date], Optional[date]]:
    """Try to extract a date range (from, to) from text.

    Looks for patterns like:
      - "July 1 - August 31"
      - "available 7/1 through 8/31"
      - "July - September"
    """
    if not text:
        return None, None

    clean = text.lower().strip()
    clean = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", clean)

    # Pattern: "Month Day - Month Day" or "Month Day to Month Day"
    range_pattern = re.compile(
        r"([a-z]+\s+\d{1,2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)"
        r"\s*(?:-|–|to|through|thru|until|til)\s*"
        r"([a-z]+\s+\d{1,2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)"
    )
    match = range_pattern.search(clean)
    if match:
        start = parse_date(match.group(1))
        end = parse_date(match.group(2))
        return start, end

    # Pattern: "Month - Month" (no day, assume 1st and last day)
    month_range = re.compile(
        r"([a-z]+)\s*(?:-|–|to|through|thru)\s*([a-z]+)"
    )
    match = month_range.search(clean)
    if match:
        start_month = MONTH_MAP.get(match.group(1))
        end_month = MONTH_MAP.get(match.group(2))
        if start_month and end_month:
            import calendar
            start = date(2026, start_month, 1)
            _, last_day = calendar.monthrange(2026, end_month)
            end = date(2026, end_month, last_day)
            return start, end

    return None, None
