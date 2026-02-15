"""Tests for parsers — price, date, location, structured."""

from datetime import date

import pytest

from parsers.price_parser import extract_price_from_text, parse_price
from parsers.date_parser import extract_date_range, parse_date
from parsers.location_parser import extract_neighborhood
from parsers.structured_parser import (
    detect_listing_type,
    extract_apartment_details,
    extract_furnished,
)
from models.enums import Borough, ListingType


class TestParsePrice:
    def test_simple_dollar(self):
        assert parse_price("$1800") == 1800

    def test_with_comma(self):
        assert parse_price("$1,800") == 1800

    def test_k_format(self):
        assert parse_price("$1.8k") == 1800

    def test_per_week(self):
        result = parse_price("$450/week")
        assert result is not None
        assert 1900 <= result <= 2000  # 450 * 4.33

    def test_per_night(self):
        result = parse_price("$65/night")
        assert result is not None
        assert result == 1950  # 65 * 30

    def test_none_input(self):
        assert parse_price("") is None
        assert parse_price(None) is None

    def test_extract_from_text(self):
        assert extract_price_from_text("Beautiful studio for $1800/mo in Midtown") == 1800

    def test_extract_from_text_no_price(self):
        assert extract_price_from_text("Beautiful studio in Midtown") is None


class TestParseDate:
    def test_month_day(self):
        assert parse_date("July 1") == date(2026, 7, 1)

    def test_month_day_ordinal(self):
        assert parse_date("July 1st") == date(2026, 7, 1)

    def test_us_format(self):
        assert parse_date("7/1") == date(2026, 7, 1)

    def test_us_format_with_year(self):
        assert parse_date("7/1/2026") == date(2026, 7, 1)

    def test_iso_format(self):
        assert parse_date("2026-07-01") == date(2026, 7, 1)

    def test_abbreviated_month(self):
        assert parse_date("Jul 1") == date(2026, 7, 1)

    def test_none_input(self):
        assert parse_date("") is None

    def test_date_range(self):
        start, end = extract_date_range("July 1 - August 31")
        assert start == date(2026, 7, 1)
        assert end == date(2026, 8, 31)

    def test_date_range_to(self):
        start, end = extract_date_range("July 1 to September 30")
        assert start == date(2026, 7, 1)
        assert end == date(2026, 9, 30)

    def test_month_range(self):
        start, end = extract_date_range("July - September")
        assert start is not None
        assert end is not None
        assert start.month == 7
        assert end.month == 9


class TestExtractNeighborhood:
    def test_midtown_east(self):
        name, borough = extract_neighborhood("Beautiful apartment in Midtown East")
        assert name == "Midtown East"
        assert borough == Borough.MANHATTAN

    def test_les_alias(self):
        name, borough = extract_neighborhood("Sunny room on the LES")
        assert name == "Lower East Side"
        assert borough == Borough.MANHATTAN

    def test_williamsburg(self):
        name, borough = extract_neighborhood("Loft in Williamsburg, Brooklyn")
        assert name == "Williamsburg"
        assert borough == Borough.BROOKLYN

    def test_lic(self):
        name, borough = extract_neighborhood("Studio in LIC near subway")
        assert name == "Long Island City"
        assert borough == Borough.QUEENS

    def test_unknown(self):
        name, borough = extract_neighborhood("Apartment somewhere nice")
        assert borough == Borough.UNKNOWN


class TestDetectListingType:
    def test_studio(self):
        assert detect_listing_type("Cozy studio apartment") == ListingType.STUDIO

    def test_one_br(self):
        assert detect_listing_type("1 bedroom sublet") == ListingType.ONE_BEDROOM

    def test_two_br(self):
        assert detect_listing_type("2br apartment available") == ListingType.TWO_BEDROOM

    def test_room(self):
        assert detect_listing_type("Private room in shared apartment") == ListingType.ROOM_IN_SHARED

    def test_hotel(self):
        assert detect_listing_type("Extended stay hotel suite") == ListingType.HOTEL_EXTENDED_STAY

    def test_unknown(self):
        assert detect_listing_type("Nice place available") == ListingType.UNKNOWN


class TestExtractApartmentDetails:
    def test_3b2ba(self):
        assert extract_apartment_details("3 bed 2 bath apartment") == "3b2ba"

    def test_1br(self):
        assert extract_apartment_details("Spacious 1 bedroom") == "1br"

    def test_studio(self):
        assert extract_apartment_details("Large studio") == "Studio"

    def test_none(self):
        assert extract_apartment_details("Nice place") == ""


class TestExtractFurnished:
    def test_furnished(self):
        assert extract_furnished("Fully furnished studio") is True

    def test_unfurnished(self):
        assert extract_furnished("Unfurnished apartment") is False

    def test_unknown(self):
        assert extract_furnished("Nice apartment") is None
