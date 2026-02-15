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
- **Firecrawl REST API** via httpx — website scraping (LeaseBreak, SpareRoom, etc.)
- **feedparser** — Craigslist RSS feed
- **gspread + google-auth** — Google Sheets API (service account)
- **pydantic / pydantic-settings** — data models and config
- **thefuzz** — fuzzy string matching for cross-source dedup
- **GitHub Actions** — scheduled runs (websites hourly, FB every 2 hours)

## Directory Structure

```
config/          Settings, neighborhood mappings, scoring weights
scrapers/        One scraper per data source (all inherit from base.py)
parsers/         LLM parser for FB posts, rule-based for structured sites
models/          Pydantic Listing model + enums
scoring/         Rating algorithm (price/location/type/timing/bonus)
dedup/           Fingerprint generation + Google Sheet-backed seen-store
sheets/          gspread client wrapper, append/sync logic
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

# Dry run (scrape + score, don't write to sheet)
python main.py --dry-run
```

## Environment Setup

Required in `.env`:
- `APIFY_API_TOKEN` — from apify.com
- `ANTHROPIC_API_KEY` — for Claude Haiku FB post parsing
- `FIRECRAWL_API_KEY` — for website scraping
- `GOOGLE_SHEETS_CREDENTIALS_FILE` — path to service account JSON
- `SPREADSHEET_ID` — Google Sheet ID from the URL

## Data Sources

| Source | Method | Frequency |
|--------|--------|-----------|
| Facebook Groups (5) | Apify actor | Every 2 hours |
| Craigslist NYC | RSS feed | Hourly |
| LeaseBreak | Firecrawl | Hourly |
| SpareRoom | Firecrawl | Hourly |
| Listings Project | Firecrawl | Hourly |
| Furnished Finder | Firecrawl | Hourly |
| Roomi | Firecrawl | Hourly |

## Rating Algorithm (1.0 – 10.0)

Weighted composite score:
- **Location (30%):** Tier 1 (Midtown East/GCT) = 10, Tier 2 (LES) = 8, Tier 3 (Other Downtown) = 6.5, Tier 4 (UES/UWS) = 5, Tier 5 (BK/Queens) = 3.5
- **Price (25%):** Under $1,500 = 9-10, $1,500-$1,850 = 7-8, $1,850-$2,000 = 5-7, over $2,000 = penalized
- **Type (20%):** Studio/1BR = 9-10, Hotel = 7, Room = 4.5
- **Timing (15%):** Full July-Sept coverage = 10, partial overlap scored proportionally
- **Bonus (10%):** Furnished, photos, trusted source, contact info

## Key Design Decisions

- **Sheet-backed dedup** (not SQLite): GitHub Actions is stateless, so fingerprints persist in a hidden `_seen` worksheet in the same Google Sheet. No external DB needed.
- **Claude Haiku for FB posts**: Facebook posts are unstructured text. The LLM extracts price, neighborhood, dates, and listing type into structured JSON.
- **Firecrawl REST API** (not MCP): The scraper runs autonomously via GitHub Actions, not inside an LLM agent context. Direct API calls via httpx are used instead of MCP tools.
- **Fail-open per source**: If one scraper fails (site down, rate limited, etc.), others still run. Errors are logged but don't crash the pipeline.
- **Status column never overwritten**: The Google Sheet Status column (A) is user-managed. New listings are always appended; existing rows are never modified.

## Running Tests

```bash
pytest tests/ -v
```
