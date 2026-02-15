"""Rating algorithm weights and tier configurations.

These are separated from the scoring logic so they're easy to tune.
"""

# Overall dimension weights (must sum to 1.0)
WEIGHTS = {
    "price": 0.25,
    "location": 0.30,
    "type": 0.20,
    "timing": 0.15,
    "bonus": 0.10,
}

# Location scoring tiers: neighborhood list → score (0-10)
# Tier 1: Midtown East / near Grand Central
# Tier 2: LES / East Village
# Tier 3: Other Midtown / Downtown
# Tier 4: UES / UWS
# Tier 5: Brooklyn / Queens commuter areas
LOCATION_TIERS: dict[int, list[str]] = {
    1: [
        "Midtown East", "Murray Hill", "Turtle Bay", "Kips Bay",
        "Tudor City", "Sutton Place",
    ],
    2: [
        "Lower East Side", "East Village", "Nolita",
        "Alphabet City", "Two Bridges",
    ],
    3: [
        "Midtown", "Midtown West", "Hell's Kitchen", "Chelsea", "Flatiron",
        "Gramercy", "Union Square", "NoMad", "Hudson Yards",
        "West Village", "Greenwich Village", "SoHo", "NoHo", "Tribeca",
        "Financial District", "Battery Park City", "Chinatown", "Little Italy",
    ],
    4: [
        "Upper East Side", "Yorkville", "Lenox Hill", "Carnegie Hill",
        "Upper West Side",
    ],
    5: [
        "Williamsburg", "DUMBO", "Brooklyn Heights", "Downtown Brooklyn",
        "Fort Greene", "Clinton Hill", "Park Slope", "Cobble Hill",
        "Boerum Hill", "Carroll Gardens", "Prospect Heights",
        "Greenpoint", "Bushwick", "Bed-Stuy",
        "Long Island City", "Astoria", "Sunnyside",
    ],
}

LOCATION_TIER_SCORES: dict[int, float] = {
    1: 10.0,
    2: 8.0,
    3: 6.5,
    4: 5.0,
    5: 3.5,
}

# Borough-level fallback scores (when neighborhood isn't recognized)
BOROUGH_FALLBACK_SCORES = {
    "Manhattan": 5.0,
    "Brooklyn": 3.0,
    "Queens": 2.5,
    "Bronx": 1.5,
    "Staten Island": 1.0,
    "Unknown": 2.0,
}

# Type scoring
TYPE_SCORES = {
    "Studio": 10.0,
    "1BR": 9.0,
    "2BR": 6.0,
    "3BR+": 5.0,
    "Hotel/Extended Stay": 7.0,
    "Room in Shared": 4.5,
    "Unknown": 3.0,
}

# Trusted/curated sources that get a bonus
TRUSTED_SOURCES = {"LeaseBreak", "Listings Project", "Furnished Finder"}
