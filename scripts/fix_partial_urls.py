"""One-time fix: replace partial URLs in the Google Sheet Link column with full URLs.

Also strips query-string junk (e.g. ?similarRental=true&moveDate=...) from
Furnished Finder URLs so links are clean.

Usage:
    python scripts/fix_partial_urls.py
    python scripts/fix_partial_urls.py --dry-run   # preview without writing
"""

import sys
from urllib.parse import urlparse

from config.settings import Settings
from sheets.client import get_gspread_client, open_spreadsheet

DOMAIN_MAP = {
    "/property/": "https://www.furnishedfinder.com",
    "/short-term-rental-details/": "https://www.leasebreak.com",
}


def clean_url(value: str) -> str | None:
    """Return a cleaned full URL if the value needs fixing, else None."""
    if not value:
        return None

    # Case 1: partial URL starting with /
    if value.startswith("/"):
        for prefix, domain in DOMAIN_MAP.items():
            if value.startswith(prefix):
                path = value.split("?")[0]  # strip query params
                return domain + path
        return None

    # Case 2: full Furnished Finder URL with query-string junk
    if "furnishedfinder.com/property/" in value and "?" in value:
        parsed = urlparse(value)
        cleaned = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if cleaned != value:
            return cleaned

    return None


def main():
    dry_run = "--dry-run" in sys.argv

    settings = Settings()
    client = get_gspread_client(settings.google_sheets_credentials_file)
    spreadsheet = open_spreadsheet(client, settings.spreadsheet_id)
    worksheet = spreadsheet.sheet1

    # Read the Link column (L = column 12)
    link_col = worksheet.col_values(12)

    fixes = []  # (row_number, old_value, new_value)
    for i, value in enumerate(link_col):
        if i == 0:
            continue  # skip header
        new_value = clean_url(value)
        if new_value:
            fixes.append((i + 1, value, new_value))  # 1-indexed row

    if not fixes:
        print("No URLs to fix — everything looks clean.")
        return

    print(f"Found {len(fixes)} URL(s) to fix:")
    for row, old, new in fixes:
        print(f"  Row {row}: {old} -> {new}")

    if dry_run:
        print("\nDry run — no changes written.")
        return

    # Batch update all cells
    import gspread as _gspread

    cells = []
    for row, _old, new in fixes:
        cells.append(_gspread.Cell(row=row, col=12, value=new))

    worksheet.update_cells(cells, value_input_option="USER_ENTERED")
    print(f"\nUpdated {len(fixes)} URL(s) in the sheet.")


if __name__ == "__main__":
    main()
