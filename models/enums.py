from enum import Enum


class ListingSource(str, Enum):
    FACEBOOK = "Facebook"
    CRAIGSLIST = "Craigslist"
    LEASEBREAK = "LeaseBreak"
    SPAREROOM = "SpareRoom"
    LISTINGS_PROJECT = "Listings Project"
    FURNISHED_FINDER = "Furnished Finder"
    ROOMI = "Roomi"


class ListingType(str, Enum):
    STUDIO = "Studio"
    ONE_BEDROOM = "1BR"
    TWO_BEDROOM = "2BR"
    THREE_PLUS_BEDROOM = "3BR+"
    ROOM_IN_SHARED = "Room in Shared"
    HOTEL_EXTENDED_STAY = "Hotel/Extended Stay"
    UNKNOWN = "Unknown"


class Borough(str, Enum):
    MANHATTAN = "Manhattan"
    BROOKLYN = "Brooklyn"
    QUEENS = "Queens"
    BRONX = "Bronx"
    STATEN_ISLAND = "Staten Island"
    UNKNOWN = "Unknown"
