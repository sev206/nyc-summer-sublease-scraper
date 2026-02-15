from datetime import date

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API keys
    apify_api_token: str = ""
    anthropic_api_key: str = ""
    firecrawl_api_key: str = ""

    # Google Sheets
    google_sheets_credentials_file: str = "config/service_account.json"
    spreadsheet_id: str = ""

    # Facebook groups
    facebook_group_urls: list[str] = [
        "https://www.facebook.com/groups/I9150/",
        "https://www.facebook.com/groups/nycroom/",
        "https://www.facebook.com/groups/1651982041751861/",
        "https://www.facebook.com/groups/nycsublets/",
        "https://www.facebook.com/groups/I1895/",
    ]

    # Scraping behavior
    max_listings_per_source: int = 100
    scrape_delay_seconds: int = 2

    # Budget and dates
    max_budget: int = 2000
    target_start_date: date = date(2026, 7, 1)
    target_end_date_min: date = date(2026, 8, 31)
    target_end_date_ideal: date = date(2026, 9, 30)

    # Logging
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
