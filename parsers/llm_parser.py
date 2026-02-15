"""LLM-based parser for unstructured Facebook posts.

Uses Claude Haiku to extract structured listing data from free-form text.
"""

import json
import logging
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a data extraction assistant. Given a Facebook post about an NYC apartment sublet/rental, extract the following fields as JSON.

If a field cannot be determined from the text, use null. Be conservative — only extract what is clearly stated.

Return ONLY valid JSON with these exact keys:
{
  "price_monthly": <integer or null — monthly rent in USD. Convert weekly (×4.33) or nightly (×30) to monthly.>,
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
}

Post text:
---
{post_text}
---"""


class LLMParser:
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def parse_facebook_post(self, post_text: str) -> Optional[dict]:
        """Parse a Facebook post into structured listing data.

        Returns a dict with extracted fields, or None if parsing fails.
        """
        if not post_text or len(post_text.strip()) < 20:
            return None

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                temperature=0.0,
                messages=[
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT.format(
                            post_text=post_text[:2000]  # Limit input size
                        ),
                    }
                ],
            )

            # Extract text content from response
            text = response.content[0].text.strip()

            # Handle cases where the model wraps JSON in markdown code blocks
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            return json.loads(text)

        except json.JSONDecodeError as e:
            logger.warning(f"LLM returned invalid JSON: {e}")
            return None
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing FB post: {e}")
            return None
