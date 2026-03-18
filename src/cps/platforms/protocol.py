"""Platform plugin protocols and shared data types.

Defines the contract for platform-specific fetchers and parsers.
Any new platform (Best Buy, Walmart, etc.) implements these protocols.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, runtime_checkable

RawData = bytes | dict[str, Any]


@dataclass(frozen=True)
class PriceRecord:
    """A single price observation from any platform."""

    price_type: str
    recorded_date: date
    price_cents: int
    source: str


@dataclass(frozen=True)
class PriceSummaryData:
    """Aggregated price summary for one price_type."""

    price_type: str
    lowest_price: int | None = None
    lowest_date: date | None = None
    highest_price: int | None = None
    highest_date: date | None = None
    current_price: int | None = None
    current_date: date | None = None


@dataclass(frozen=True)
class FetchResult:
    """Result of fetching raw data from a platform."""

    raw_data: RawData
    storage_path: str | None = None


@dataclass(frozen=True)
class ParseResult:
    """Result of parsing raw platform data into price records."""

    records: list[PriceRecord]
    summaries: list[PriceSummaryData] = field(default_factory=list)
    points_extracted: int = 0
    confidence: float | None = None
    validation_passed: bool | None = None
    validation_status: str = "success"


@runtime_checkable
class PlatformFetcher(Protocol):
    """Fetches raw data from a platform for a given product."""

    async def fetch(self, platform_id: str) -> FetchResult: ...


@runtime_checkable
class PlatformParser(Protocol):
    """Parses raw platform data into structured price records."""

    def parse(self, fetch_result: FetchResult) -> ParseResult: ...
