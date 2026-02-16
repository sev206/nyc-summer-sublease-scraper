"""One-time cleanup script: fix Craigslist prices/dates and re-score all listings.

Reads the Google Sheet, re-scrapes Craigslist listing pages for accurate
rent_period/dates/furnished info, then re-scores ALL listings.

Usage:
    python -m scripts.cleanup_sheet              # Full cleanup
    python -m scripts.cleanup_sheet --dry-run    # Preview changes without writing
"""

import argparse
import logging
import sys
import time
from datetime import date

import httpx
from bs4 import BeautifulSoup

from config.settings import Settings
from models.enums import Borough, ListingSource, ListingType
from models.listing import Listing
from scoring.rating import compute_rating
from scrapers.craigslist import parse_craigslist_listing_page, _adjust_price_for_period
from sheets.client import get_gspread_client, open_spreadsheet

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Column indices (1-based, matching SHEET_HEADERS)
COL_STATUS = 1
COL_RATING = 2
COL_PRICE = 3
COL_NEIGHBORHOOD = 4
COL_BOROUGH = 5
COL_TYPE = 6
COL_DETAILS = 7
COL_AVAIL_FROM = 8
COL_AVAIL_TO = 9
COL_FURNISHED = 10
COL_SOURCE = 11
COL_LINK = 12
COL_DESCRIPTION = 13
COL_BREAKDOWN = 14
COL_CONTACT = 15
COL_SCRAPED_AT = 16
COL_LISTING_ID = 17


def fetch_craigslist_details(url: str) -> dict | None:
    """Fetch a Craigslist listing page and return parsed details."""
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        return parse_craigslist_listing_page(response.text)
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def row_to_listing(row: list[str]) -> Listing | None:
    """Reconstruct a minimal Listing from a sheet row for re-scoring."""
    try:
        # Pad row to expected length
        while len(row) < 17:
            row.append("")

        price_raw = row[COL_PRICE - 1]
        price = None
        if price_raw and price_raw != "N/A":
            try:
                price = int(float(str(price_raw).replace(",", "").replace("$", "")))
            except (ValueError, TypeError):
                pass

        # Parse source
        source_str = row[COL_SOURCE - 1]
        try:
            source = ListingSource(source_str)
        except ValueError:
            source = ListingSource.CRAIGSLIST

        # Parse borough
        borough_str = row[COL_BOROUGH - 1]
        try:
            borough = Borough(borough_str)
        except ValueError:
            borough = Borough.UNKNOWN

        # Parse listing type
        type_str = row[COL_TYPE - 1]
        try:
            listing_type = ListingType(type_str)
        except ValueError:
            listing_type = ListingType.UNKNOWN

        # Parse dates
        avail_from = _parse_date_str(row[COL_AVAIL_FROM - 1])
        avail_to = _parse_date_str(row[COL_AVAIL_TO - 1])

        # Parse furnished
        furnished_str = row[COL_FURNISHED - 1]
        is_furnished = True if furnished_str == "Yes" else (
            False if furnished_str == "No" else None
        )

        return Listing(
            source=source,
            source_url=row[COL_LINK - 1],
            price_monthly=price,
            price_raw=str(price_raw),
            neighborhood=row[COL_NEIGHBORHOOD - 1],
            borough=borough,
            listing_type=listing_type,
            apartment_details=row[COL_DETAILS - 1],
            is_furnished=is_furnished,
            available_from=avail_from,
            available_to=avail_to,
            description=row[COL_DESCRIPTION - 1],
            contact_info=row[COL_CONTACT - 1],
        )
    except Exception as e:
        logger.warning(f"Failed to parse row: {e}")
        return None


def _parse_date_str(s: str) -> date | None:
    """Parse a date string from the sheet (ISO format)."""
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def main(dry_run: bool = False) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    settings = Settings()

    # Connect to sheet
    gc = get_gspread_client(settings.google_sheets_credentials_file)
    spreadsheet = open_spreadsheet(gc, settings.spreadsheet_id)
    worksheet = spreadsheet.sheet1

    # Read all data
    all_rows = worksheet.get_all_values()
    if not all_rows:
        logger.info("Sheet is empty")
        return

    header = all_rows[0]
    data_rows = all_rows[1:]
    logger.info(f"Loaded {len(data_rows)} rows from sheet")

    # Track changes for batch update
    updates: list[dict] = []  # {"row": row_num, "col": col_num, "value": value}

    # Phase 1: Re-scrape Craigslist listings for accurate data
    cl_rows = [
        (i + 2, row) for i, row in enumerate(data_rows)
        if len(row) > COL_SOURCE - 1 and row[COL_SOURCE - 1] == "Craigslist"
    ]
    logger.info(f"Found {len(cl_rows)} Craigslist listings to check")

    fixed_prices = 0
    fixed_dates = 0
    fixed_furnished = 0

    for row_num, row in cl_rows:
        url = row[COL_LINK - 1] if len(row) > COL_LINK - 1 else ""
        if not url:
            continue

        details = fetch_craigslist_details(url)
        if not details:
            continue

        current_price_str = row[COL_PRICE - 1] if len(row) > COL_PRICE - 1 else ""
        current_price = None
        if current_price_str and current_price_str != "N/A":
            try:
                current_price = int(
                    float(str(current_price_str).replace(",", "").replace("$", ""))
                )
            except (ValueError, TypeError):
                pass

        # Fix price if rent period is not monthly
        rent_period = details.get("rent_period")
        if rent_period and rent_period != "monthly" and current_price:
            new_price = _adjust_price_for_period(current_price, rent_period)
            if new_price and new_price != current_price:
                logger.info(
                    f"  Row {row_num}: ${current_price} ({rent_period}) -> "
                    f"${new_price}/mo ({url})"
                )
                updates.append({"row": row_num, "col": COL_PRICE, "value": new_price})
                # Update the in-memory row for re-scoring
                row[COL_PRICE - 1] = str(new_price)
                fixed_prices += 1

        # Fix available_from if missing
        if not row[COL_AVAIL_FROM - 1] and details.get("available_from"):
            avail_from = details["available_from"]
            updates.append({
                "row": row_num, "col": COL_AVAIL_FROM,
                "value": str(avail_from),
            })
            row[COL_AVAIL_FROM - 1] = str(avail_from)
            fixed_dates += 1

        # Fix available_to if missing
        if not row[COL_AVAIL_TO - 1] and details.get("available_to"):
            avail_to = details["available_to"]
            updates.append({
                "row": row_num, "col": COL_AVAIL_TO,
                "value": str(avail_to),
            })
            row[COL_AVAIL_TO - 1] = str(avail_to)

        # Fix furnished if missing
        if not row[COL_FURNISHED - 1] and details.get("is_furnished") is not None:
            val = "Yes" if details["is_furnished"] else "No"
            updates.append({"row": row_num, "col": COL_FURNISHED, "value": val})
            row[COL_FURNISHED - 1] = val
            fixed_furnished += 1

        # Fix description if it's just the title (very short)
        current_desc = row[COL_DESCRIPTION - 1] if len(row) > COL_DESCRIPTION - 1 else ""
        if details.get("description") and len(current_desc) < 100:
            new_desc = details["description"][:300]
            updates.append({
                "row": row_num, "col": COL_DESCRIPTION, "value": new_desc,
            })
            row[COL_DESCRIPTION - 1] = new_desc

        # Be polite to Craigslist
        time.sleep(1.5)

    logger.info(
        f"Craigslist fixes: {fixed_prices} prices, {fixed_dates} dates, "
        f"{fixed_furnished} furnished"
    )

    # Phase 2: Re-score ALL listings
    logger.info("Re-scoring all listings...")
    rescored = 0
    for i, row in enumerate(data_rows):
        row_num = i + 2  # 1-based, skip header

        listing = row_to_listing(row)
        if not listing:
            continue

        rating, breakdown = compute_rating(listing, settings)
        breakdown_str = " ".join(
            f"{k[0].upper()}:{v}" for k, v in breakdown.items()
        )

        current_rating = row[COL_RATING - 1] if len(row) > COL_RATING - 1 else ""
        try:
            current_rating_float = float(current_rating) if current_rating else 0.0
        except ValueError:
            current_rating_float = 0.0

        if abs(rating - current_rating_float) > 0.05:
            updates.append({"row": row_num, "col": COL_RATING, "value": rating})
            updates.append({
                "row": row_num, "col": COL_BREAKDOWN, "value": breakdown_str,
            })
            rescored += 1

    logger.info(f"Re-scored {rescored} listings with changed ratings")

    # Phase 3: Apply updates to sheet
    if dry_run:
        logger.info(f"DRY RUN: Would apply {len(updates)} cell updates")
        for u in updates[:30]:
            logger.info(f"  Row {u['row']}, Col {u['col']}: {u['value']}")
        if len(updates) > 30:
            logger.info(f"  ... and {len(updates) - 30} more")
        return

    if not updates:
        logger.info("No updates needed")
        return

    logger.info(f"Applying {len(updates)} cell updates to sheet...")

    # Batch updates by converting to cell list for efficiency
    cells = []
    for u in updates:
        cells.append(gspread_cell(u["row"], u["col"], u["value"]))

    # Use batch update for efficiency (max 60k cells per call)
    worksheet.update_cells(cells, value_input_option="USER_ENTERED")

    # Re-sort by rating
    row_count = len(worksheet.col_values(1))
    if row_count > 1:
        worksheet.sort((2, "des"), range=f"A2:Q{row_count}")
        logger.info("Re-sorted sheet by rating")

    logger.info("Cleanup complete!")


def gspread_cell(row: int, col: int, value):
    """Create a gspread Cell object."""
    import gspread
    cell = gspread.Cell(row=row, col=col, value=value)
    return cell


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleanup sheet data")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without writing to sheet",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
