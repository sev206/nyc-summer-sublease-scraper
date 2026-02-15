"""Tests for the rating algorithm."""

from datetime import date

import pytest

from config.settings import Settings
from models.enums import Borough, ListingSource, ListingType
from models.listing import Listing
from scoring.rating import (
    compute_rating,
    score_bonus,
    score_location,
    score_price,
    score_timing,
    score_type,
)


class TestScorePrice:
    def test_exceptional_deal(self):
        assert score_price(1000) == 10.0

    def test_great_deal(self):
        assert score_price(1400) == 9.0

    def test_good_deal(self):
        assert score_price(1600) == 8.0

    def test_solid(self):
        assert score_price(1800) == 7.0

    def test_at_budget(self):
        score = score_price(1950)
        assert 5.0 <= score <= 7.0

    def test_over_budget(self):
        assert score_price(2100) == 2.0

    def test_way_over(self):
        assert score_price(3000) == 0.0

    def test_unknown(self):
        assert score_price(None) == 4.0

    def test_at_exact_budget(self):
        score = score_price(2000)
        assert score >= 5.0


class TestScoreLocation:
    def test_tier1_midtown_east(self):
        assert score_location("Midtown East", "Manhattan") == 10.0

    def test_tier1_murray_hill(self):
        assert score_location("Murray Hill", "Manhattan") == 10.0

    def test_tier2_les(self):
        assert score_location("Lower East Side", "Manhattan") == 8.0

    def test_tier2_east_village(self):
        assert score_location("East Village", "Manhattan") == 8.0

    def test_tier3_chelsea(self):
        assert score_location("Chelsea", "Manhattan") == 6.5

    def test_tier3_soho(self):
        assert score_location("SoHo", "Manhattan") == 6.5

    def test_tier4_ues(self):
        assert score_location("Upper East Side", "Manhattan") == 5.0

    def test_tier5_williamsburg(self):
        assert score_location("Williamsburg", "Brooklyn") == 3.5

    def test_tier5_lic(self):
        assert score_location("Long Island City", "Queens") == 3.5

    def test_unknown_manhattan(self):
        assert score_location("", "Manhattan") == 5.0

    def test_unknown_brooklyn(self):
        assert score_location("", "Brooklyn") == 3.0

    def test_completely_unknown(self):
        assert score_location("", "Unknown") == 2.0


class TestScoreType:
    def test_studio(self):
        assert score_type("Studio") == 10.0

    def test_one_br(self):
        assert score_type("1BR") == 9.0

    def test_hotel(self):
        assert score_type("Hotel/Extended Stay") == 7.0

    def test_room(self):
        assert score_type("Room in Shared") == 4.5

    def test_unknown(self):
        assert score_type("Unknown") == 3.0


class TestScoreTiming:
    def test_perfect_coverage(self):
        """July 1 through September 30 = best possible."""
        score = score_timing(
            date(2026, 7, 1), date(2026, 9, 30),
            date(2026, 7, 1), date(2026, 9, 30),
        )
        assert score >= 9.0

    def test_july_august(self):
        """July-August only = good but missing September."""
        score = score_timing(
            date(2026, 7, 1), date(2026, 8, 31),
            date(2026, 7, 1), date(2026, 9, 30),
        )
        assert 5.0 <= score <= 9.0

    def test_no_overlap(self):
        """Completely outside the target window."""
        score = score_timing(
            date(2026, 1, 1), date(2026, 3, 31),
            date(2026, 7, 1), date(2026, 9, 30),
        )
        assert score == 0.0

    def test_unknown_dates(self):
        score = score_timing(None, None, date(2026, 7, 1), date(2026, 9, 30))
        assert score == 5.0

    def test_late_start_penalty(self):
        """Starting 2 weeks late should be penalized."""
        score = score_timing(
            date(2026, 7, 15), date(2026, 9, 30),
            date(2026, 7, 1), date(2026, 9, 30),
        )
        good_score = score_timing(
            date(2026, 7, 1), date(2026, 9, 30),
            date(2026, 7, 1), date(2026, 9, 30),
        )
        assert score < good_score


class TestScoreBonus:
    def test_fully_loaded(self):
        listing = Listing(
            source=ListingSource.LEASEBREAK,
            is_furnished=True,
            images=["img1.jpg"],
            address="123 Main St",
            contact_info="test@email.com",
        )
        assert score_bonus(listing) >= 8.0

    def test_bare_minimum(self):
        listing = Listing(source=ListingSource.CRAIGSLIST)
        assert score_bonus(listing) == 0.0


class TestComputeRating:
    def test_dream_listing(self):
        """Studio in Midtown East, $1600/mo, July-Sept, furnished, from LeaseBreak."""
        settings = Settings()
        listing = Listing(
            source=ListingSource.LEASEBREAK,
            price_monthly=1600,
            neighborhood="Midtown East",
            borough=Borough.MANHATTAN,
            listing_type=ListingType.STUDIO,
            available_from=date(2026, 7, 1),
            available_to=date(2026, 8, 31),
            is_furnished=True,
            images=["img.jpg"],
            source_url="https://leasebreak.com/listing/123",
        )
        rating, breakdown = compute_rating(listing, settings)
        assert rating >= 8.0
        assert breakdown["location"] == 10.0
        assert breakdown["type"] == 10.0
        assert breakdown["price"] == 8.0

    def test_mediocre_listing(self):
        """Room in Brooklyn, $1900/mo, unknown dates."""
        settings = Settings()
        listing = Listing(
            source=ListingSource.CRAIGSLIST,
            price_monthly=1900,
            neighborhood="Bushwick",
            borough=Borough.BROOKLYN,
            listing_type=ListingType.ROOM_IN_SHARED,
            source_url="https://craigslist.org/123",
        )
        rating, breakdown = compute_rating(listing, settings)
        assert rating < 5.0
