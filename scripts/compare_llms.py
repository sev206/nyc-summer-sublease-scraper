"""Compare LLM extraction quality: Claude Haiku vs GPT-4.1 Nano vs Gemini 2.5 Flash Lite.

Uses the exact same prompts from parsers/llm_parser.py against realistic test data.
Calls all three APIs via httpx (no extra SDKs needed).

Usage:
    # Set API keys in environment or .env
    python scripts/compare_llms.py
"""

import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")

# ---------------------------------------------------------------------------
# Test data — realistic samples matching actual scraper output
# ---------------------------------------------------------------------------

SAMPLE_FB_POST = """
Hey everyone! Subletting my studio in Midtown East (E 45th & 2nd Ave) for the
summer. Available July 1 through September 15. $1,750/month, fully furnished
with AC, WiFi, doorman building. 5 min walk to Grand Central. Laundry in
building. DM me for pics and details! Serious inquiries only.
"""

SAMPLE_LISTING_PAGE = """
# Beautiful Furnished Studio - Murray Hill

**$1,900/month** | Available July 1, 2026 - August 31, 2026

Charming fully furnished studio apartment in the heart of Murray Hill, Manhattan.
Walking distance to Grand Central Terminal and multiple subway lines.

**Details:**
- Studio apartment, 1 bathroom
- 450 sq ft
- Fully furnished (bed, couch, desk, kitchenware)
- Central AC and heating
- Laundry in building
- Doorman building
- Pets not allowed

**Location:** 220 E 36th St, Murray Hill, Manhattan, NY 10016

**Contact:** Email landlord at rentals@example.com or call (212) 555-0147

**Lease Terms:** Minimum 2 month sublet. July 1 - August 31 preferred.
"""

# ---------------------------------------------------------------------------
# Prompts (copied from parsers/llm_parser.py)
# ---------------------------------------------------------------------------

FB_PROMPT = """You are a data extraction assistant. Given a Facebook post about an NYC apartment sublet/rental, extract the following fields as JSON.

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

LISTING_PROMPT = """You are extracting apartment rental listings from a scraped search results page from {source_name}.

Today's date is 2026-02-17. Analyze the page content below and extract ALL individual apartment/room listings you can find. Return a JSON array of listing objects.

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
- For dates: use YYYY-MM-DD format. If only month is mentioned (e.g. "July"), assume the 1st. If a date says "available now", use 2026-02-17. Assume year 2026 unless otherwise specified.
- Return ONLY a valid JSON array. No other text before or after.
- If no valid listings are found, return []

Page content from {source_name}:
---
{page_content}
---"""

# ---------------------------------------------------------------------------
# API callers
# ---------------------------------------------------------------------------

def call_anthropic(prompt: str, max_tokens: int = 1024) -> dict:
    """Call Claude Haiku 4.5 via Anthropic API."""
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30.0,
    )
    r.raise_for_status()
    data = r.json()
    text = data["content"][0]["text"]
    usage = data.get("usage", {})
    return {
        "text": text,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


def call_openai(prompt: str, max_tokens: int = 1024) -> dict:
    """Call GPT-4.1 Nano via OpenAI API."""
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4.1-nano",
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30.0,
    )
    r.raise_for_status()
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return {
        "text": text,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }


def call_gemini(prompt: str, max_tokens: int = 1024) -> dict:
    """Call Gemini 2.5 Flash Lite via Google AI API."""
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash-lite:generateContent?key={GEMINI_KEY}",
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
    r.raise_for_status()
    data = r.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    usage = data.get("usageMetadata", {})
    return {
        "text": text,
        "input_tokens": usage.get("promptTokenCount", 0),
        "output_tokens": usage.get("candidatesTokenCount", 0),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_json(text: str) -> str:
    """Strip markdown code fences from JSON output."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


def parse_json_safe(text: str):
    """Parse JSON from LLM output, returning None on failure."""
    try:
        return json.loads(clean_json(text))
    except json.JSONDecodeError:
        return None


MODELS = {
    "Claude Haiku 4.5": call_anthropic,
    "GPT-4.1 Nano": call_openai,
    "Gemini 2.5 Flash Lite": call_gemini,
}

COST_PER_M = {
    "Claude Haiku 4.5": {"input": 1.00, "output": 5.00},
    "GPT-4.1 Nano": {"input": 0.10, "output": 0.40},
    "Gemini 2.5 Flash Lite": {"input": 0.10, "output": 0.40},
}


def run_test(test_name: str, prompt: str):
    """Run a single prompt through all three models and compare."""
    print(f"\n{'='*70}")
    print(f"TEST: {test_name}")
    print(f"{'='*70}")

    results = {}
    for name, caller in MODELS.items():
        key_check = {
            "Claude Haiku 4.5": ANTHROPIC_KEY,
            "GPT-4.1 Nano": OPENAI_KEY,
            "Gemini 2.5 Flash Lite": GEMINI_KEY,
        }
        if not key_check[name]:
            print(f"\n--- {name}: SKIPPED (no API key) ---")
            continue

        print(f"\n--- {name} ---")
        try:
            start = time.time()
            result = caller(prompt)
            elapsed = time.time() - start

            parsed = parse_json_safe(result["text"])
            cost_in = result["input_tokens"] / 1_000_000 * COST_PER_M[name]["input"]
            cost_out = result["output_tokens"] / 1_000_000 * COST_PER_M[name]["output"]
            total_cost = cost_in + cost_out

            results[name] = {
                "parsed": parsed,
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "cost": total_cost,
                "latency": elapsed,
                "valid_json": parsed is not None,
            }

            print(f"  Latency: {elapsed:.2f}s")
            print(f"  Tokens: {result['input_tokens']} in / {result['output_tokens']} out")
            print(f"  Cost: ${total_cost:.6f}")
            print(f"  Valid JSON: {'YES' if parsed is not None else 'NO'}")
            if parsed is not None:
                print(f"  Output: {json.dumps(parsed, indent=2)}")
            else:
                print(f"  Raw output: {result['text'][:500]}")

        except Exception as e:
            print(f"  ERROR: {e}")
            results[name] = {"error": str(e)}

    return results


def print_summary(all_results: dict):
    """Print a summary comparison table."""
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")

    for test_name, results in all_results.items():
        print(f"\n{test_name}:")
        print(f"  {'Model':<25} {'JSON OK':<10} {'Latency':<10} {'Cost':<12}")
        print(f"  {'-'*57}")
        for model, data in results.items():
            if "error" in data:
                print(f"  {model:<25} {'ERROR':<10} {'-':<10} {'-':<12}")
            else:
                ok = "YES" if data["valid_json"] else "NO"
                lat = f"{data['latency']:.2f}s"
                cost = f"${data['cost']:.6f}"
                print(f"  {model:<25} {ok:<10} {lat:<10} {cost:<12}")

    # Monthly projection
    print(f"\n{'='*70}")
    print("MONTHLY COST PROJECTION (estimated 630 calls/day)")
    print(f"{'='*70}")
    daily_calls = 630
    for model in MODELS:
        # Average tokens across all tests for this model
        total_in = 0
        total_out = 0
        count = 0
        for results in all_results.values():
            if model in results and "input_tokens" in results[model]:
                total_in += results[model]["input_tokens"]
                total_out += results[model]["output_tokens"]
                count += 1
        if count > 0:
            avg_in = total_in / count
            avg_out = total_out / count
            daily_cost = daily_calls * (
                avg_in / 1_000_000 * COST_PER_M[model]["input"]
                + avg_out / 1_000_000 * COST_PER_M[model]["output"]
            )
            monthly_cost = daily_cost * 30
            print(f"  {model:<25} ~${monthly_cost:.2f}/month")


def main():
    missing = []
    if not ANTHROPIC_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not OPENAI_KEY:
        missing.append("OPENAI_API_KEY")
    if not GEMINI_KEY:
        missing.append("GOOGLE_API_KEY or GEMINI_API_KEY")

    if missing:
        print(f"Warning: Missing API keys: {', '.join(missing)}")
        print("Those models will be skipped.\n")

    all_results = {}

    # Test 1: Facebook post extraction
    fb_prompt = FB_PROMPT.format(post_text=SAMPLE_FB_POST)
    all_results["FB Post Extraction"] = run_test("Facebook Post Extraction", fb_prompt)

    # Test 2: Listing page extraction
    listing_prompt = LISTING_PROMPT.format(
        source_name="LeaseBreak NYC Sublet",
        page_content=SAMPLE_LISTING_PAGE,
    )
    all_results["Listing Page Extraction"] = run_test(
        "Listing Page Extraction", listing_prompt
    )

    print_summary(all_results)


if __name__ == "__main__":
    main()
