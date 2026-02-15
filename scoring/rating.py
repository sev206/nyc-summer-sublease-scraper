"""Rating algorithm — scores listings 1.0 to 10.0 based on user preferences."""

from datetime import date
from typing import Optional

from config.scoring_weights import (
    BOROUGH_FALLBACK_SCORES,
    LOCATION_TIER_SCORES,
    LOCATION_TIERS,
    TRUSTED_SOURCES,
    TYPE_SCORES,
    WEIGHTS,
)
from config.settings import Settings
from models.enums import ListingSource
from models.listing import Listing


def compute_rating(listing: Listing, settings: Settings) -> tuple[float, dict]:
    """Compute a 1.0-10.0 composite rating and per-dimension breakdown."""
    breakdown = {
        "price": score_price(listing.price_monthly),
        "location": score_location(listing.neighborhood, listing.borough.value),
        "type": score_type(listing.listing_type.value),
        "timing": score_timing(
            listing.available_from,
            listing.available_to,
            settings.target_start_date,
            settings.target_end_date_ideal,
        ),
        "bonus": score_bonus(listing),
    }

    composite = sum(breakdown[dim] * WEIGHTS[dim] for dim in WEIGHTS)
    composite = round(max(1.0, min(10.0, composite)), 1)

    return composite, breakdown


def score_price(price_monthly: Optional[int]) -> float:
    """Score based on monthly price. Budget cap is $2,000.

    ≤$1,200 → 10.0 (exceptional)
    $1,200-$1,500 → 9.0
    $1,500-$1,700 → 8.0
    $1,700-$1,850 → 7.0
    $1,850-$2,000 → 5.0-7.0 (linear)
    $2,000-$2,200 → 2.0 (over budget but close)
    >$2,200 → 0.0
    Unknown → 4.0
    """
    if price_monthly is None:
        return 4.0
    if price_monthly <= 1200:
        return 10.0
    if price_monthly <= 1500:
        return 9.0
    if price_monthly <= 1700:
        return 8.0
    if price_monthly <= 1850:
        return 7.0
    if price_monthly <= 2000:
        return 5.0 + 2.0 * (2000 - price_monthly) / 150
    if price_monthly <= 2200:
        return 2.0
    return 0.0


def score_location(neighborhood: str, borough: str) -> float:
    """Score based on location tier preferences."""
    if not neighborhood:
        return BOROUGH_FALLBACK_SCORES.get(borough, 2.0)

    # Exact match against tier lists
    for tier, neighborhoods in LOCATION_TIERS.items():
        for n in neighborhoods:
            if n.lower() == neighborhood.lower():
                return LOCATION_TIER_SCORES[tier]

    # Fuzzy/partial match
    neighborhood_lower = neighborhood.lower()
    for tier, neighborhoods in LOCATION_TIERS.items():
        for n in neighborhoods:
            if n.lower() in neighborhood_lower or neighborhood_lower in n.lower():
                return LOCATION_TIER_SCORES[tier]

    return BOROUGH_FALLBACK_SCORES.get(borough, 2.0)


def score_type(listing_type: str) -> float:
    """Score based on listing type preferences."""
    return TYPE_SCORES.get(listing_type, 3.0)


def score_timing(
    available_from: Optional[date],
    available_to: Optional[date],
    target_start: date,
    target_end: date,
) -> float:
    """Score based on date overlap with target window.

    Full July-September coverage → 10.0
    Full July-August coverage → 9.0
    Good overlap → 7.0-8.5
    Partial → 3.0-6.0
    No overlap → 0.0
    Unknown → 5.0
    """
    if available_from is None and available_to is None:
        return 5.0

    # Default missing dates generously
    start = available_from or date(2026, 6, 1)
    end = available_to or date(2026, 12, 31)

    # Calculate overlap
    overlap_start = max(start, target_start)
    overlap_end = min(end, target_end)

    if overlap_start > overlap_end:
        return 0.0

    target_days = (target_end - target_start).days
    if target_days == 0:
        return 5.0

    overlap_days = (overlap_end - overlap_start).days
    coverage_ratio = overlap_days / target_days

    # Penalty for not being available by July 1
    start_penalty = 0.0
    if start > target_start:
        days_late = (start - target_start).days
        if days_late > 7:
            start_penalty = min(3.0, days_late * 0.2)

    # Bonus for covering through September
    target_end_ideal = date(2026, 9, 30)
    end_bonus = 0.0
    if end >= target_end_ideal:
        end_bonus = 1.0
    elif end >= date(2026, 8, 31):
        end_bonus = 0.5

    score = (coverage_ratio * 8.0) + end_bonus - start_penalty
    return max(0.0, min(10.0, score))


def score_bonus(listing: Listing) -> float:
    """Bonus for desirable attributes: furnished, photos, trusted source, contact info."""
    score = 0.0

    if listing.is_furnished:
        score += 3.0

    if listing.images:
        score += 2.0

    if listing.source.value in TRUSTED_SOURCES:
        score += 2.0

    if listing.address:
        score += 1.5

    if listing.contact_info:
        score += 1.5

    return min(10.0, score)
