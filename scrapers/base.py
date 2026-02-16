"""Abstract base class for all scrapers."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from config.settings import Settings
from models.listing import Listing

if TYPE_CHECKING:
    from sheets.sync import SheetSync


class BaseScraper(ABC):
    """Base class that all source scrapers inherit from."""

    def __init__(
        self,
        settings: Settings,
        known_urls: set[str] | None = None,
        sheet_sync: "SheetSync | None" = None,
    ):
        self.settings = settings
        self.known_urls = known_urls or set()
        self.sheet_sync = sheet_sync

    @abstractmethod
    def scrape(self) -> list[Listing]:
        """Scrape the source and return normalized Listing objects."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name of this source."""
        ...
