"""LLM-based parser for unstructured text - Facebook posts and search result pages.

Uses Gemini 2.5 Flash Lite to extract structured listing data from free-form text.
"""

import json
import logging
from datetime import date
from typing import Optional

import httpx

from config.neighborhoods import get_borough, normalize_neighborhood
from models.enums import Borough, ListingSource, ListingType
from models.listing import Listing

logger = logging.getLogger(__name__)

# --- Prompts ---

EXTRACTION_PROMPT = """You are a data extraction assistant. Given a Facebook post about an NYC apartment sublet/rental, extract the following fields as JSON.

If a field cannot be determined from the text, use null. Be conservative - only extract what is clearly stated.

Return ONLY valid JSON with these exact keys:
{{
  "price_monthly": <integer or null - monthly rent in USD. Convert weekly (*4.33) or nightly (*30) to monthly.>,
  "price_raw": "<original price string as written in the post>",
  "neighborhood": "<NYC neighborhood name, e.g. 'Midtown East', 'Lower East Side', 'Williamsburg'>",
  "borough": "<Manhattan|Brooklyn|Queens|Bronx|Staten Island|null>",
  "address": "<exact street address if mentioned, else null>",
  "listing_type": "<studio|1br|2br|3br+|room_in_shared|hotel_extended_stay|null>",
  "apartment_details": "<e.g. '2b1ba', 'studio', '3br/2ba', or null>",
  "is_furnished": <true|false|null>,
  "available_from": "<YYYY-MM-DD or null>",
  "available_to": "<YYYY-MM-DD or null>",
  "description_summary": "<1-2 sentence summary of the listing>",
  "contact_info": "<email, phone, or 'DM' if they say to message them, else null>",
  "is_iso": <true if this is someone LOOKING for housing (not offering), false if offering>
}}

Post text:
---
{post_text}
---"""

LISTINGS_PAGE_PROMPT = """You are extracting apartment rental listings from a scraped search results page from {source_name}.

Today's date is 2026-02-15. Analyze the page content below and extract ALL individual apartment/room listings you can find. Return a JSON array of listing objects.

Each listing object should have:
{{
  "title": "<listing title or short description>",
  "price_monthly": <integer monthly rent in USD, or null. Convert weekly (*4.33) or nightly (*30) or daily (*30).>,
  "price_raw": "<original price text as shown>",
  "neighborhood": "<NYC neighborhood name or null>",
  "borough": "<Manhattan|Brooklyn|Queens|Bronx|Staten Island|null>",
  "listing_type": "<studio|1br|2br|3br+|room_in_shared|hotel_extended_stay|null>",
  "apartment_details": "<e.g. '2b1ba', 'studio', '1br', or null>",
  "is_furnished": <true|false|null>,
  "available_from": "<YYYY-MM-DD or null - the earliest move-in date>",
  "available_to": "<YYYY-MM-DD or null - the lease end / move-out date>",
  "source_url": "<direct URL link to this specific listing, or null>",
  "description": "<1-2 sentence summary of the listing>",
  "contact_info": "<email, phone, or null>"
}}

Rules:
- Extract ONLY actual apartment/room rental listings being offered
- Skip page navigation, ads, site headers/footers, search filters
- Skip "in search of" / "looking for" posts
- Each listing on the page should be a separate object in the array
- If a price is per week, multiply by 4.33 and round to integer. If per night or per day, multiply by 30.
- For dates: use YYYY-MM-DD format. If only month is mentioned (e.g. "July"), assume the 1st. If a date says "available now", use 2026-02-15. Assume year 2026 unless otherwise specified.
- Return ONLY a valid JSON array. No other text before or after.
- If no valid listings are found, return []

Page content from {source_name}:
---
{page_content}
---"""

# --- Enum mappings ---

TYPE_MAP = {
    "studio": ListingType.STUDIO,
    "1br": ListingType.ONE_BEDROOM,
    "2br": ListingType.TWO_BEDROOM,
    "3br+": ListingType.THREE_PLUS_BEDROOM,
    "room_in_shared": ListingType.ROOM_IN_SHARED,
    "hotel_extended_stay": ListingType.HOTEL_EXTENDED_STAY,
}

BOROUGH_MAP = {
    "manhattan": Borough.MANHATTAN,
    "brooklyn": Borough.BROOKLYN,
    "queens": Borough.QUEENS,
    "bronx": Borough.BRONX,
    "staten island": Borough.STATEN_ISLAND,
}


def _parse_date_str(date_str: Optional[str]) -> Optional[date]:
    """Parse a YYYY-MM-DD date string into a date object."""
    if not date_str:
        return None
    try:
        parts = date_str.split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def listing_from_parsed(
    parsed: dict,
    source: ListingSource,
    default_furnished: Optional[bool] = None,
    default_type: Optional[ListingType] = None,
) -> Listing:
    """Convert an LLM-parsed dict into a Listing object."""
    # Map borough
    borough = Borough.UNKNOWN
    if parsed.get("borough"):
        borough = BOROUGH_MAP.get(parsed["borough"].lower(), Borough.UNKNOWN)

    # Normalize neighborhood
    neighborhood = ""
    if parsed.get("neighborhood"):
        neighborhood = normalize_neighborhood(parsed["neighborhood"])
        detected_borough = get_borough(neighborhood)
        if detected_borough != Borough.UNKNOWN:
            borough = detected_borough

    # Map listing type
    listing_type = default_type or ListingType.UNKNOWN
    if parsed.get("listing_type"):
        listing_type = TYPE_MAP.get(
            parsed["listing_type"].lower(), listing_type
        )

    # Furnished
    is_furnished = parsed.get("is_furnished")
    if is_furnished is None and default_furnished is not None:
        is_furnished = default_furnished

    return Listing(
        source=source,
        source_url=parsed.get("source_url", "") or "",
        title=parsed.get("title", "") or "",
        price_monthly=parsed.get("price_monthly"),
        price_raw=parsed.get("price_raw", "") or "",
        neighborhood=neighborhood,
        borough=borough,
        address=parsed.get("address", "") or "",
        listing_type=listing_type,
        apartment_details=parsed.get("apartment_details", "") or "",
        is_furnished=is_furnished,
        available_from=_parse_date_str(parsed.get("available_from")),
        available_to=_parse_date_str(parsed.get("available_to")),
        description=parsed.get("description", "") or parsed.get("description_summary", "") or "",
        contact_info=parsed.get("contact_info", "") or "",
    )


class LLMParser:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite"):
        self.api_key = api_key
        self.model = model
        self._api_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )

    def _call_gemini(self, prompt: str, max_tokens: int = 1024) -> str:
        """Call the Gemini API and return the text response."""
        response = httpx.post(
            self._api_url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": max_tokens,
                },
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def parse_facebook_post(self, post_text: str) -> Optional[dict]:
        """Parse a Facebook post into structured listing data."""
        if not post_text or len(post_text.strip()) < 20:
            return None

        try:
            text = self._call_gemini(
                EXTRACTION_PROMPT.format(post_text=post_text[:2000]),
                max_tokens=500,
            )
            text = self._clean_json(text.strip())
            return json.loads(text)

        except json.JSONDecodeError as e:
            logger.warning(f"LLM returned invalid JSON: {e}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"Gemini API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing FB post: {e}")
            return None

    def parse_listings_page(
        self, markdown: str, source_name: str, max_chars: int = 15000
    ) -> list[dict]:
        """Parse a search results page markdown into a list of listing dicts.

        For large pages, splits into chunks and processes each separately
        to avoid LLM output truncation.
        """
        if not markdown or len(markdown.strip()) < 50:
            return []

        content = markdown[:max_chars]

        # Split large pages into chunks to avoid output truncation
        chunk_size = 12000
        if len(content) > chunk_size:
            chunks = []
            for i in range(0, len(content), chunk_size):
                chunk = content[i : i + chunk_size]
                if len(chunk.strip()) > 100:
                    chunks.append(chunk)
        else:
            chunks = [content]

        all_listings = []
        for i, chunk in enumerate(chunks):
            chunk_label = f"{source_name} (chunk {i + 1}/{len(chunks)})" if len(chunks) > 1 else source_name
            results = self._parse_single_chunk(chunk, source_name, chunk_label)
            all_listings.extend(results)

        logger.info(
            f"LLM extracted {len(all_listings)} total listings from {source_name}"
        )
        return all_listings

    def _parse_single_chunk(
        self, page_content: str, source_name: str, chunk_label: str
    ) -> list[dict]:
        """Parse a single chunk of page content into listing dicts."""
        try:
            text = self._call_gemini(
                LISTINGS_PAGE_PROMPT.format(
                    source_name=source_name,
                    page_content=page_content,
                ),
                max_tokens=8192,
            )
            text = self._clean_json(text.strip())
            result = json.loads(text)

            if isinstance(result, list):
                logger.info(
                    f"  LLM extracted {len(result)} listings from {chunk_label}"
                )
                return result
            else:
                logger.warning(f"LLM returned non-array for {chunk_label}")
                return []

        except json.JSONDecodeError as e:
            logger.warning(f"LLM returned invalid JSON for {chunk_label}: {e}")
            return []
        except httpx.HTTPStatusError as e:
            logger.error(f"Gemini API error for {chunk_label}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing {chunk_label}: {e}")
            return []

    def _clean_json(self, text: str) -> str:
        """Remove markdown code block wrappers from JSON text."""
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return text
