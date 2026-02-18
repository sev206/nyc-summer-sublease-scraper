"""Google Sheets client wrapper."""

import json
import logging
import os
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_HEADERS = [
    "Status", "Rating", "Price", "Neighborhood", "Borough", "Type",
    "Apartment Details", "Available From", "Available To", "Furnished",
    "Source", "Link", "Description", "Rating Breakdown", "Contact",
    "Scraped At", "Listing ID",
]


def get_gspread_client(credentials_path: str) -> gspread.Client:
    """Create an authenticated gspread client.

    Supports both a JSON file path and a JSON string (for GitHub Actions
    where the service account JSON is stored as a secret).
    """
    # Check if it's a JSON string (from env var) or a file path
    if credentials_path.strip().startswith("{"):
        info = json.loads(credentials_path)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    elif os.environ.get("GOOGLE_SHEETS_CREDS", "").strip().startswith("{"):
        info = json.loads(os.environ["GOOGLE_SHEETS_CREDS"])
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)

    return gspread.authorize(creds)


def open_spreadsheet(
    client: gspread.Client, spreadsheet_id: str
) -> gspread.Spreadsheet:
    """Open a spreadsheet by ID."""
    return client.open_by_key(spreadsheet_id)


def ensure_headers(worksheet: gspread.Worksheet) -> None:
    """Ensure the header row exists."""
    first_row = worksheet.row_values(1)
    if not first_row or first_row[0] != SHEET_HEADERS[0]:
        worksheet.insert_row(SHEET_HEADERS, index=1)
        logger.info("Wrote header row to worksheet")


def ensure_log_worksheet(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    """Get or create the _log worksheet for scraper monitoring."""
    try:
        return spreadsheet.worksheet("_log")
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet("_log", rows=5000, cols=5)
        ws.update("A1:E1", [["Timestamp", "Source", "Group URL", "Posts Returned", "Limit"]])
        logger.info("Created _log worksheet for scraper monitoring")
        return ws


def ensure_seen_worksheet(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    """Get or create the _seen worksheet for dedup persistence."""
    try:
        return spreadsheet.worksheet("_seen")
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet("_seen", rows=10000, cols=3)
        ws.update("A1:C1", [["fingerprint", "source", "first_seen"]])
        logger.info("Created _seen worksheet for dedup persistence")
        return ws


def ensure_fb_state_worksheet(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    """Get or create the _fb_state worksheet for per-group scrape timestamps."""
    try:
        return spreadsheet.worksheet("_fb_state")
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet("_fb_state", rows=100, cols=2)
        ws.update("A1:B1", [["group_url", "last_scrape_utc"]])
        logger.info("Created _fb_state worksheet for Facebook scrape timestamps")
        return ws
