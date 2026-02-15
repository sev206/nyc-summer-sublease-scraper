"""Abstract base class for all scrapers."""

from abc import ABC, abstractmethod

from config.settings import Settings
from models.listing import Listing


class BaseScraper(ABC):
    """Base class that all source scrapers inherit from."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    def scrape(self) -> list[Listing]:
        """Scrape the source and return normalized Listing objects."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name of this source."""
        ...
