# NYC Apartment Sublet Scraper

## Project Overview

Automated scraper that finds NYC apartment sublets for a summer stay (July 1 – end of August/September 2026). It scrapes multiple data sources on a schedule, normalizes and deduplicates listings, scores them against user preferences, and appends new ones to a Google Sheet.

**Budget:** $2,000/month max
**Dates:** July 1 – August 31 or September 30, 2026
**Ideal location:** Midtown East / near Grand Central

## Tech Stack

- **Python 3.12**
- **apify-client** — Facebook Groups scraping
- **anthropic** SDK — Claude Haiku for parsing unstructured FB posts
- **Firecrawl REST API** via httpx — website scraping (LeaseBreak, Furnished Finder, etc.)
- **httpx + beautifulsoup4** — Craigslist HTML scraping
- **gspread + google-auth** — Google Sheets API (service account)
- **pydantic / pydantic-settings** — data models and config
- **thefuzz** — fuzzy string matching for cross-source dedup
- **GitHub Actions** — scheduled runs (websites 5x/day, FB 3x/day)

## Directory Structure

```
config/          Settings, neighborhood mappings, scoring weights
scrapers/        One scraper per data source (all inherit from base.py)
parsers/         LLM parser for FB posts, rule-based for structured sites
models/          Pydantic Listing model + enums
scoring/         Rating algorithm (price/location/type/timing/bonus)
dedup/           Fingerprint generation + Google Sheet-backed seen-store
sheets/          gspread client wrapper, append/sync logic
scripts/         Utility scripts (cleanup_sheet.py)
main.py          Pipeline orchestrator
tests/           pytest tests
.github/workflows/  Cron-scheduled GitHub Actions
```

## How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# Copy .env.example to .env and fill in API keys
cp .env.example .env

# Run all scrapers
python main.py

# Run a single source
python main.py --source craigslist

# Run multiple sources
python main.py --sources craigslist,leasebreak,furnished_finder

# Dry run (scrape + score, don't write to sheet)
python main.py --dry-run
```

Available source names: `craigslist`, `leasebreak`, `furnished_finder`, `spareroom`, `listings_project`, `roomi`, `facebook`

## Environment Setup

Required in `.env`:
- `APIFY_API_TOKEN` — from apify.com
- `ANTHROPIC_API_KEY` — for Claude Haiku FB post parsing
- `FIRECRAWL_API_KEY` — for website scraping
- `GOOGLE_SHEETS_CREDENTIALS_FILE` — path to service account JSON
- `SPREADSHEET_ID` — Google Sheet ID from the URL

## Data Sources

| Source | Method | Scheduled | Notes |
|--------|--------|-----------|-------|
| Facebook Groups (5) | Apify actor + Gemini Flash Lite | 3x/day (8am, 1pm, 6pm EST) | Dynamic time window, limit 50/group |
| Craigslist NYC | httpx + BeautifulSoup | 5x/day | Fetches individual listing pages |
| LeaseBreak | Firecrawl | 5x/day | Per-borough, paginated |
| Furnished Finder | Firecrawl | 5x/day | Per-borough, paginated |
| SpareRoom | Firecrawl | Not scheduled | Scraper exists but dropped from workflows |
| Listings Project | Firecrawl | Not scheduled | Scraper exists but dropped from workflows |
| Roomi | Firecrawl | Not scheduled | Scraper exists but not in any workflow |

## Rating Algorithm (1.0 – 10.0)

Weighted composite score:
- **Location (30%):** Tier 1 (Midtown East/GCT) = 10, Tier 2 (LES) = 8, Tier 3 (Other Downtown) = 6.5, Tier 4 (UES/UWS) = 5, Tier 5 (BK/Queens) = 3.5
- **Price (25%):** Under $1,500 = 9-10, $1,500-$1,850 = 7-8, $1,850-$2,000 = 5-7, over $2,000 = penalized
- **Type (20%):** Studio/1BR = 9-10, Hotel = 7, Room = 4.5
- **Timing (15%):** Full July-Sept coverage = 10, partial overlap scored proportionally
- **Bonus (10%):** Furnished, photos, trusted source, contact info

## Key Design Decisions

- **Sheet-backed dedup** (not SQLite): GitHub Actions is stateless, so fingerprints persist in a `_seen` worksheet in the same Google Sheet. No external DB needed.
- **Hit-limit monitoring**: When a Facebook group returns exactly the `resultsLimit` count, a warning is logged to the `_log` worksheet (auto-created on first run).
- **Claude Haiku for FB posts**: Facebook posts are unstructured text. The LLM extracts price, neighborhood, dates, and listing type into structured JSON.
- **Firecrawl REST API** (not MCP): The scraper runs autonomously via GitHub Actions, not inside an LLM agent context. Direct API calls via httpx are used instead of MCP tools.
- **Fail-open per source**: If one scraper fails (site down, rate limited, etc.), others still run. Errors are logged but don't crash the pipeline.
- **Status column never overwritten**: The Google Sheet Status column (A) is user-managed. New listings are always appended; existing rows are never modified.
- **Dynamic FB scrape windows** (not fixed): Per-group last-scrape timestamps are stored in the `_fb_state` worksheet. Each run computes the exact elapsed time + 15-min buffer as the `onlyPostsNewerThan` value, so Apify fetches only posts since the last scrape. The `resultsLimit` of 50 is a safety ceiling — Apify charges per post returned, not per limit set. If Apify costs become prohibitive, Bright Data's Web Scraper API ($1.50/1K records pay-as-you-go) is a viable alternative with absolute `start_date`/`end_date` filtering. See: https://docs.brightdata.com/api-reference/web-scraper-api/social-media-apis/facebook

## Google Sheet Worksheets

| Tab | Purpose |
|-----|---------|
| Sheet1 | Main listings (17 columns: Status through Listing ID) |
| `_seen` | Dedup fingerprints (auto-created) |
| `_log` | Hit-limit warnings for FB groups (auto-created) |
| `_fb_state` | Per-group last-scrape timestamps for dynamic time windows (auto-created) |

## Running Tests

```bash
pytest tests/ -v
```
