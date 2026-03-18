# Phase 1B: New Architecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the TaskQueue Protocol, Fetcher/Parser plugin system, and ASIN discovery pipeline on top of the Phase 1A multi-platform codebase. Enables distributed workers and multi-platform extensibility.

**Architecture:** Protocol-driven plugin system — `PlatformFetcher` and `PlatformParser` protocols define the contract for any platform; `TaskQueue` protocol abstracts job scheduling (DB now, Redis later). Amazon implementation wraps existing CCC downloader + extractors. Recovery state machine preserved.

**Tech Stack:** Python 3.12+, SQLAlchemy 2.x async, PostgreSQL 16 (SELECT FOR UPDATE SKIP LOCKED), pytest, Typer CLI

**Spec reference:** `docs/superpowers/specs/2026-03-17-distributed-crawling-design.md` Sections 3.3–3.5

**Prerequisite:** Phase 1A complete, 207 tests passing. VPS needs `alembic upgrade head` for migration 003.

---

## File Structure

### New files (13)

| File | Responsibility |
|------|---------------|
| `src/cps/platforms/__init__.py` | Package init, re-exports |
| `src/cps/platforms/protocol.py` | PriceRecord, FetchResult, ParseResult, PriceSummaryData, PlatformFetcher, PlatformParser |
| `src/cps/platforms/registry.py` | get_fetcher() / get_parser() factory functions |
| `src/cps/platforms/amazon/__init__.py` | Amazon sub-package init |
| `src/cps/platforms/amazon/fetcher.py` | AmazonFetcher — wraps CccDownloader + PngStorage |
| `src/cps/platforms/amazon/parser.py` | AmazonParser — wraps PixelAnalyzer + OcrReader + Validator |
| `src/cps/queue/__init__.py` | Package init, re-exports |
| `src/cps/queue/protocol.py` | Task dataclass, TaskQueue Protocol |
| `src/cps/queue/db_queue.py` | DbTaskQueue — SELECT FOR UPDATE SKIP LOCKED |
| `src/cps/pipeline/result_store.py` | store_results() + _build_price_summary_upsert() extracted from orchestrator |
| `src/cps/discovery/__init__.py` | Package init |
| `src/cps/discovery/pipeline.py` | DiscoveryPipeline — candidate submission + no-data deactivation |
| `src/cps/worker.py` | Generic worker loop with recovery state machine |

### Modified files (3)

| File | Change |
|------|--------|
| `src/cps/pipeline/orchestrator.py` | Refactor to use TaskQueue + Fetcher + Parser + ResultStore |
| `src/cps/cli.py` | Update `crawl run` constructor, add `worker run` command |
| `tests/unit/test_orchestrator_upsert.py` | Update import path for moved `_build_price_summary_upsert` |

### New test files (9)

| File | Tests |
|------|-------|
| `tests/unit/test_platform_protocol.py` | Type creation, Protocol conformance |
| `tests/unit/test_amazon_fetcher.py` | Delegation to CccDownloader + PngStorage |
| `tests/unit/test_amazon_parser.py` | Delegation to PixelAnalyzer + OcrReader + Validator |
| `tests/unit/test_platform_registry.py` | Factory lookup, unknown platform error |
| `tests/unit/test_task_queue.py` | Task dataclass, TaskQueue Protocol conformance |
| `tests/unit/test_db_queue.py` | pop_next, complete, fail, requeue behavior |
| `tests/unit/test_result_store.py` | FetchRun creation, PriceHistory insert, PriceSummary upsert |
| `tests/unit/test_discovery_pipeline.py` | Candidate submission, no-data deactivation |
| `tests/unit/test_worker.py` | Loop behavior, error handling, shutdown |

---

### Task 1: Platform Data Types + Protocols

**Files:**
- Create: `src/cps/platforms/__init__.py`
- Create: `src/cps/platforms/protocol.py`
- Test: `tests/unit/test_platform_protocol.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_platform_protocol.py
"""Tests for platform plugin types and protocols."""

from datetime import date

import pytest

from cps.platforms.protocol import (
    FetchResult,
    ParseResult,
    PlatformFetcher,
    PlatformParser,
    PriceRecord,
    PriceSummaryData,
)


class TestPriceRecord:
    def test_frozen_dataclass(self):
        record = PriceRecord(
            price_type="amazon",
            recorded_date=date(2025, 1, 15),
            price_cents=29900,
            source="ccc_chart",
        )
        assert record.price_type == "amazon"
        assert record.price_cents == 29900

    def test_immutable(self):
        record = PriceRecord(
            price_type="amazon",
            recorded_date=date(2025, 1, 15),
            price_cents=29900,
            source="ccc_chart",
        )
        with pytest.raises(AttributeError):
            record.price_cents = 19900


class TestPriceSummaryData:
    def test_all_optional_fields_default_none(self):
        summary = PriceSummaryData(price_type="amazon")
        assert summary.lowest_price is None
        assert summary.lowest_date is None
        assert summary.highest_price is None
        assert summary.current_price is None

    def test_full_construction(self):
        summary = PriceSummaryData(
            price_type="new",
            lowest_price=15000,
            lowest_date=date(2024, 11, 29),
            highest_price=29900,
            highest_date=date(2025, 3, 1),
            current_price=19900,
            current_date=date(2025, 3, 17),
        )
        assert summary.lowest_price == 15000
        assert summary.current_date == date(2025, 3, 17)


class TestFetchResult:
    def test_bytes_raw_data(self):
        result = FetchResult(raw_data=b"\x89PNG\r\n", storage_path="/tmp/chart.png")
        assert isinstance(result.raw_data, bytes)
        assert result.storage_path == "/tmp/chart.png"

    def test_dict_raw_data(self):
        result = FetchResult(raw_data={"sku": "6525401", "price": 299.99})
        assert isinstance(result.raw_data, dict)
        assert result.storage_path is None

    def test_storage_path_defaults_none(self):
        result = FetchResult(raw_data=b"data")
        assert result.storage_path is None


class TestParseResult:
    def test_empty_records(self):
        result = ParseResult(records=[])
        assert result.records == []
        assert result.summaries == []
        assert result.points_extracted == 0
        assert result.confidence is None
        assert result.validation_passed is None
        assert result.validation_status == "success"

    def test_with_records_and_summaries(self):
        records = [
            PriceRecord("amazon", date(2025, 1, 1), 29900, "ccc_chart"),
            PriceRecord("amazon", date(2025, 2, 1), 24900, "ccc_chart"),
        ]
        summaries = [
            PriceSummaryData("amazon", lowest_price=24900, highest_price=29900),
        ]
        result = ParseResult(
            records=records,
            summaries=summaries,
            points_extracted=2,
            confidence=0.85,
            validation_passed=True,
            validation_status="success",
        )
        assert len(result.records) == 2
        assert result.points_extracted == 2


class TestProtocolConformance:
    def test_fetcher_protocol_is_runtime_checkable(self):
        class FakeFetcher:
            async def fetch(self, platform_id: str) -> FetchResult:
                return FetchResult(raw_data=b"")

        assert isinstance(FakeFetcher(), PlatformFetcher)

    def test_parser_protocol_is_runtime_checkable(self):
        class FakeParser:
            def parse(self, fetch_result: FetchResult) -> ParseResult:
                return ParseResult(records=[])

        assert isinstance(FakeParser(), PlatformParser)

    def test_non_conforming_class_fails_check(self):
        class NotAFetcher:
            def wrong_method(self):
                pass

        assert not isinstance(NotAFetcher(), PlatformFetcher)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_platform_protocol.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.platforms'`

- [ ] **Step 3: Write implementation**

```python
# src/cps/platforms/__init__.py
"""Platform plugin system — protocols, types, and registry."""
```

```python
# src/cps/platforms/protocol.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_platform_protocol.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/platforms/__init__.py src/cps/platforms/protocol.py tests/unit/test_platform_protocol.py
git commit -m "feat: add platform plugin types and protocols"
```

---

### Task 2: AmazonFetcher

**Files:**
- Create: `src/cps/platforms/amazon/__init__.py`
- Create: `src/cps/platforms/amazon/fetcher.py`
- Test: `tests/unit/test_amazon_fetcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_amazon_fetcher.py
"""Tests for AmazonFetcher — wraps CccDownloader + PngStorage."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.platforms.amazon.fetcher import AmazonFetcher
from cps.platforms.protocol import FetchResult, PlatformFetcher


class TestAmazonFetcherConformance:
    def test_implements_platform_fetcher_protocol(self):
        fetcher = AmazonFetcher(
            base_url="https://charts.example.com",
            data_dir=Path("/tmp"),
        )
        assert isinstance(fetcher, PlatformFetcher)


class TestAmazonFetcherFetch:
    @pytest.fixture
    def fetcher(self, tmp_path):
        return AmazonFetcher(
            base_url="https://charts.example.com",
            data_dir=tmp_path,
            rate_limit=10.0,
        )

    async def test_returns_fetch_result_with_png_bytes(self, fetcher):
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        with (
            patch.object(fetcher._downloader, "download", new_callable=AsyncMock, return_value=png_bytes),
            patch.object(fetcher._storage, "save", return_value=Path("/tmp/chart.png")),
        ):
            result = await fetcher.fetch("B08N5WRWNW")

        assert isinstance(result, FetchResult)
        assert result.raw_data == png_bytes
        assert result.storage_path == "/tmp/chart.png"

    async def test_delegates_to_downloader_with_platform_id(self, fetcher):
        with (
            patch.object(fetcher._downloader, "download", new_callable=AsyncMock, return_value=b"png") as mock_dl,
            patch.object(fetcher._storage, "save", return_value=Path("/tmp/x.png")),
        ):
            await fetcher.fetch("B08N5WRWNW")

        mock_dl.assert_awaited_once_with("B08N5WRWNW")

    async def test_delegates_to_storage_with_bytes(self, fetcher):
        png_bytes = b"fake-png-data"
        with (
            patch.object(fetcher._downloader, "download", new_callable=AsyncMock, return_value=png_bytes),
            patch.object(fetcher._storage, "save", return_value=Path("/tmp/x.png")) as mock_save,
        ):
            await fetcher.fetch("B08N5WRWNW")

        mock_save.assert_called_once_with("B08N5WRWNW", png_bytes)

    async def test_propagates_download_errors(self, fetcher):
        from cps.crawler.downloader import RateLimitError

        with patch.object(fetcher._downloader, "download", new_callable=AsyncMock, side_effect=RateLimitError("429")):
            with pytest.raises(RateLimitError):
                await fetcher.fetch("B08N5WRWNW")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_amazon_fetcher.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.platforms.amazon'`

- [ ] **Step 3: Write implementation**

```python
# src/cps/platforms/amazon/__init__.py
"""Amazon platform plugin — CCC chart fetcher and parser."""
```

```python
# src/cps/platforms/amazon/fetcher.py
"""Amazon platform fetcher — downloads CCC chart images."""

from pathlib import Path

from cps.crawler.downloader import CccDownloader
from cps.crawler.storage import PngStorage
from cps.platforms.protocol import FetchResult


class AmazonFetcher:
    """Fetches CCC chart PNG images for Amazon products.

    Wraps the existing CccDownloader (curl_cffi) and PngStorage.
    """

    def __init__(self, base_url: str, data_dir: Path, rate_limit: float = 1.0) -> None:
        self._downloader = CccDownloader(base_url=base_url, rate_limit=rate_limit)
        self._storage = PngStorage(data_dir=data_dir)

    async def fetch(self, platform_id: str) -> FetchResult:
        """Download a CCC chart PNG and save it to disk.

        Raises:
            RateLimitError: On HTTP 429.
            BlockedError: On HTTP 403.
            ServerError: On HTTP 500+.
            DownloadError: On connection failures.
        """
        png_bytes = await self._downloader.download(platform_id)
        chart_path = self._storage.save(platform_id, png_bytes)
        return FetchResult(raw_data=png_bytes, storage_path=str(chart_path))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_amazon_fetcher.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/platforms/amazon/__init__.py src/cps/platforms/amazon/fetcher.py tests/unit/test_amazon_fetcher.py
git commit -m "feat: add AmazonFetcher wrapping CccDownloader + PngStorage"
```

---

### Task 3: AmazonParser

**Files:**
- Create: `src/cps/platforms/amazon/parser.py`
- Test: `tests/unit/test_amazon_parser.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_amazon_parser.py
"""Tests for AmazonParser — wraps PixelAnalyzer + OcrReader + Validator."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cps.platforms.amazon.parser import AmazonParser
from cps.platforms.protocol import FetchResult, ParseResult, PlatformParser


class TestAmazonParserConformance:
    def test_implements_platform_parser_protocol(self):
        parser = AmazonParser()
        assert isinstance(parser, PlatformParser)


class TestAmazonParserParse:
    @pytest.fixture
    def parser(self):
        return AmazonParser()

    def _mock_pixel_data(self):
        return {
            "amazon": [
                (date(2025, 1, 1), 29900),
                (date(2025, 2, 1), 24900),
                (date(2025, 3, 1), 27900),
            ],
            "new": [
                (date(2025, 1, 15), 31900),
            ],
        }

    def _mock_ocr_result(self):
        ocr = MagicMock()
        ocr.confidence = 0.85
        ocr.legend = {
            "amazon": {
                "lowest": "$249.00",
                "highest": "$299.00",
                "current": "$279.00",
            },
        }
        return ocr

    def _mock_validation(self):
        v = MagicMock()
        v.passed = True
        v.status = "success"
        return v

    def test_returns_parse_result_with_records(self, parser):
        fetch_result = FetchResult(raw_data=b"png", storage_path="/tmp/chart.png")
        with (
            patch.object(parser._pixel_analyzer, "analyze", return_value=self._mock_pixel_data()),
            patch.object(parser._ocr_reader, "read", return_value=self._mock_ocr_result()),
            patch.object(parser._validator, "validate", return_value=self._mock_validation()),
        ):
            result = parser.parse(fetch_result)

        assert isinstance(result, ParseResult)
        assert len(result.records) == 4  # 3 amazon + 1 new
        assert result.points_extracted == 4

    def test_records_have_correct_source(self, parser):
        fetch_result = FetchResult(raw_data=b"png", storage_path="/tmp/chart.png")
        with (
            patch.object(parser._pixel_analyzer, "analyze", return_value=self._mock_pixel_data()),
            patch.object(parser._ocr_reader, "read", return_value=self._mock_ocr_result()),
            patch.object(parser._validator, "validate", return_value=self._mock_validation()),
        ):
            result = parser.parse(fetch_result)

        assert all(r.source == "ccc_chart" for r in result.records)

    def test_builds_summaries(self, parser):
        fetch_result = FetchResult(raw_data=b"png", storage_path="/tmp/chart.png")
        with (
            patch.object(parser._pixel_analyzer, "analyze", return_value=self._mock_pixel_data()),
            patch.object(parser._ocr_reader, "read", return_value=self._mock_ocr_result()),
            patch.object(parser._validator, "validate", return_value=self._mock_validation()),
        ):
            result = parser.parse(fetch_result)

        assert len(result.summaries) == 2  # amazon + new
        amazon_summary = next(s for s in result.summaries if s.price_type == "amazon")
        assert amazon_summary.lowest_price == 24900
        assert amazon_summary.lowest_date == date(2025, 2, 1)   # date of lowest price
        assert amazon_summary.highest_price == 29900
        assert amazon_summary.highest_date == date(2025, 1, 1)  # date of highest price
        assert amazon_summary.current_price == 27900
        assert amazon_summary.current_date == date(2025, 3, 1)  # last data point

    def test_includes_confidence_and_validation(self, parser):
        fetch_result = FetchResult(raw_data=b"png", storage_path="/tmp/chart.png")
        with (
            patch.object(parser._pixel_analyzer, "analyze", return_value=self._mock_pixel_data()),
            patch.object(parser._ocr_reader, "read", return_value=self._mock_ocr_result()),
            patch.object(parser._validator, "validate", return_value=self._mock_validation()),
        ):
            result = parser.parse(fetch_result)

        assert result.confidence == 0.85
        assert result.validation_passed is True
        assert result.validation_status == "success"

    def test_no_storage_path_returns_failed(self, parser):
        fetch_result = FetchResult(raw_data=b"png", storage_path=None)
        result = parser.parse(fetch_result)
        assert result.records == []
        assert result.validation_status == "failed"

    def test_empty_pixel_data_returns_zero_points(self, parser):
        fetch_result = FetchResult(raw_data=b"png", storage_path="/tmp/chart.png")
        ocr = MagicMock()
        ocr.confidence = 0.1
        ocr.legend = {}
        with (
            patch.object(parser._pixel_analyzer, "analyze", return_value={}),
            patch.object(parser._ocr_reader, "read", return_value=ocr),
            patch.object(parser._validator, "validate", return_value=MagicMock(passed=False, status="failed")),
        ):
            result = parser.parse(fetch_result)

        assert result.points_extracted == 0
        assert result.records == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_amazon_parser.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.platforms.amazon.parser'`

- [ ] **Step 3: Write implementation**

```python
# src/cps/platforms/amazon/parser.py
"""Amazon platform parser — extracts prices from CCC chart images.

Wraps the existing PixelAnalyzer, OcrReader, and Validator to produce
standardized PriceRecords and PriceSummaryData.
"""

from pathlib import Path

from cps.extractor.ocr_reader import OcrReader
from cps.extractor.pixel_analyzer import PixelAnalyzer
from cps.pipeline.validator import Validator
from cps.platforms.protocol import (
    FetchResult,
    ParseResult,
    PriceRecord,
    PriceSummaryData,
)


class AmazonParser:
    """Parses CCC chart PNG images into price records."""

    def __init__(self) -> None:
        self._pixel_analyzer = PixelAnalyzer()
        self._ocr_reader = OcrReader()
        self._validator = Validator()

    def parse(self, fetch_result: FetchResult) -> ParseResult:
        """Extract price data from a CCC chart image.

        Args:
            fetch_result: Must have storage_path set to the saved PNG path.

        Returns:
            ParseResult with records, summaries, and validation metadata.
        """
        if fetch_result.storage_path is None:
            return ParseResult(records=[], validation_status="failed")

        chart_path = Path(fetch_result.storage_path)

        pixel_data = self._pixel_analyzer.analyze(chart_path)
        ocr_result = self._ocr_reader.read(chart_path)

        # Build OCR comparison data for cross-validation
        ocr_compare: dict[str, dict[str, int]] = {}
        for price_type, legend_vals in ocr_result.legend.items():
            ocr_compare[price_type] = {}
            for key, val in legend_vals.items():
                if val and val.startswith("$"):
                    try:
                        cents = int(float(val.replace("$", "").replace(",", "")) * 100)
                        ocr_compare[price_type][key] = cents
                    except (ValueError, TypeError):
                        pass

        # Build pixel summary for validation
        pixel_summary: dict[str, dict[str, int]] = {}
        for price_type, points in pixel_data.items():
            if points:
                prices = [p for _, p in points]
                pixel_summary[price_type] = {
                    "lowest": min(prices),
                    "highest": max(prices),
                    "current": prices[-1],
                }

        validation = self._validator.validate(pixel_summary, ocr_compare)

        # Build PriceRecords from pixel data
        records: list[PriceRecord] = []
        for price_type, points in pixel_data.items():
            for recorded_date, price_cents in points:
                records.append(
                    PriceRecord(
                        price_type=price_type,
                        recorded_date=recorded_date,
                        price_cents=price_cents,
                        source="ccc_chart",
                    )
                )

        # Build PriceSummaryData — use dates corresponding to actual min/max prices
        summaries: list[PriceSummaryData] = []
        for price_type, summary in pixel_summary.items():
            pts = pixel_data.get(price_type, [])
            if pts:
                min_pair = min(pts, key=lambda p: p[1])  # (date, price) with lowest price
                max_pair = max(pts, key=lambda p: p[1])  # (date, price) with highest price
                last_pair = pts[-1]
            else:
                min_pair = max_pair = last_pair = (None, None)
            summaries.append(
                PriceSummaryData(
                    price_type=price_type,
                    lowest_price=summary.get("lowest"),
                    lowest_date=min_pair[0],
                    highest_price=summary.get("highest"),
                    highest_date=max_pair[0],
                    current_price=summary.get("current"),
                    current_date=last_pair[0],
                )
            )

        total_points = sum(len(pts) for pts in pixel_data.values())

        return ParseResult(
            records=records,
            summaries=summaries,
            points_extracted=total_points,
            confidence=ocr_result.confidence,
            validation_passed=validation.passed,
            validation_status=validation.status,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_amazon_parser.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/platforms/amazon/parser.py tests/unit/test_amazon_parser.py
git commit -m "feat: add AmazonParser wrapping PixelAnalyzer + OcrReader + Validator"
```

---

### Task 4: Platform Registry

**Files:**
- Create: `src/cps/platforms/registry.py`
- Test: `tests/unit/test_platform_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_platform_registry.py
"""Tests for platform registry — factory functions."""

from pathlib import Path

import pytest

from cps.platforms.amazon.fetcher import AmazonFetcher
from cps.platforms.amazon.parser import AmazonParser
from cps.platforms.protocol import PlatformFetcher, PlatformParser
from cps.platforms.registry import get_fetcher, get_parser


class TestGetFetcher:
    def test_amazon_returns_amazon_fetcher(self, tmp_path):
        fetcher = get_fetcher(
            "amazon",
            base_url="https://charts.example.com",
            data_dir=tmp_path,
        )
        assert isinstance(fetcher, AmazonFetcher)
        assert isinstance(fetcher, PlatformFetcher)

    def test_amazon_passes_rate_limit(self, tmp_path):
        fetcher = get_fetcher(
            "amazon",
            base_url="https://charts.example.com",
            data_dir=tmp_path,
            rate_limit=2.5,
        )
        assert isinstance(fetcher, AmazonFetcher)

    def test_unknown_platform_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown platform"):
            get_fetcher("ebay", base_url="x", data_dir=tmp_path)


class TestGetParser:
    def test_amazon_returns_amazon_parser(self):
        parser = get_parser("amazon")
        assert isinstance(parser, AmazonParser)
        assert isinstance(parser, PlatformParser)

    def test_unknown_platform_raises(self):
        with pytest.raises(ValueError, match="Unknown platform"):
            get_parser("ebay")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_platform_registry.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.platforms.registry'`

- [ ] **Step 3: Write implementation**

```python
# src/cps/platforms/registry.py
"""Platform plugin registry — factory functions for fetchers and parsers."""

from pathlib import Path

from cps.platforms.protocol import PlatformFetcher, PlatformParser


def get_fetcher(platform: str, **kwargs: object) -> PlatformFetcher:
    """Create the appropriate fetcher for a platform.

    Args:
        platform: Platform name ("amazon", "bestbuy", etc.)
        **kwargs: Platform-specific configuration:
            - amazon: base_url (str), data_dir (Path), rate_limit (float, optional)

    Raises:
        ValueError: If platform is unknown.
    """
    if platform == "amazon":
        from cps.platforms.amazon.fetcher import AmazonFetcher

        return AmazonFetcher(
            base_url=str(kwargs["base_url"]),
            data_dir=Path(str(kwargs["data_dir"])),
            rate_limit=float(kwargs.get("rate_limit", 1.0)),
        )
    raise ValueError(f"Unknown platform: {platform}")


def get_parser(platform: str) -> PlatformParser:
    """Create the appropriate parser for a platform.

    Raises:
        ValueError: If platform is unknown.
    """
    if platform == "amazon":
        from cps.platforms.amazon.parser import AmazonParser

        return AmazonParser()
    raise ValueError(f"Unknown platform: {platform}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_platform_registry.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/platforms/registry.py tests/unit/test_platform_registry.py
git commit -m "feat: add platform registry with factory functions"
```

---

### Task 5: Task Dataclass + TaskQueue Protocol

**Files:**
- Create: `src/cps/queue/__init__.py`
- Create: `src/cps/queue/protocol.py`
- Test: `tests/unit/test_task_queue.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_task_queue.py
"""Tests for task queue types and protocol."""

import pytest

from cps.queue.protocol import Task, TaskQueue


class TestTask:
    def test_frozen_dataclass(self):
        task = Task(id=1, product_id=42, platform_id="B08N5WRWNW", platform="amazon")
        assert task.id == 1
        assert task.platform_id == "B08N5WRWNW"
        assert task.platform == "amazon"

    def test_immutable(self):
        task = Task(id=1, product_id=42, platform_id="B08N5WRWNW", platform="amazon")
        with pytest.raises(AttributeError):
            task.id = 2


class TestTaskQueueProtocol:
    def test_conforming_class_passes_check(self):
        class FakeQueue:
            async def pop_next(self, platform: str) -> Task | None:
                return None

            async def complete(self, task_id: int) -> None:
                pass

            async def fail(self, task_id: int, error: str) -> None:
                pass

            async def requeue(self, task_id: int) -> None:
                pass

        assert isinstance(FakeQueue(), TaskQueue)

    def test_non_conforming_class_fails_check(self):
        class NotAQueue:
            async def pop(self):
                pass

        assert not isinstance(NotAQueue(), TaskQueue)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_task_queue.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.queue'`

- [ ] **Step 3: Write implementation**

```python
# src/cps/queue/__init__.py
"""Task queue system — protocol and implementations."""
```

```python
# src/cps/queue/protocol.py
"""Task queue protocol and shared types.

The TaskQueue protocol abstracts job scheduling. Current implementation
uses PostgreSQL (DbTaskQueue); swappable to Redis with ~50 lines of code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Task:
    """A unit of work from the queue."""

    id: int
    product_id: int
    platform_id: str
    platform: str


@runtime_checkable
class TaskQueue(Protocol):
    """Abstract task queue for crawl job scheduling."""

    async def pop_next(self, platform: str) -> Task | None:
        """Atomically claim the next pending task for the given platform."""
        ...

    async def complete(self, task_id: int) -> None:
        """Mark a task as completed and schedule the next crawl."""
        ...

    async def fail(self, task_id: int, error: str) -> None:
        """Mark a task as failed with retry logic."""
        ...

    async def requeue(self, task_id: int) -> None:
        """Return a task to pending without penalty (for transient errors)."""
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_task_queue.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/queue/__init__.py src/cps/queue/protocol.py tests/unit/test_task_queue.py
git commit -m "feat: add Task dataclass and TaskQueue protocol"
```

---

### Task 6: DbTaskQueue

**Files:**
- Create: `src/cps/queue/db_queue.py`
- Test: `tests/unit/test_db_queue.py`

**Important:** This uses `SELECT FOR UPDATE SKIP LOCKED` — the key enabler for safe multi-worker concurrency. Unit tests use mocked sessions; integration tests against a real DB are deferred to the integration test suite.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_db_queue.py
"""Tests for DbTaskQueue — PostgreSQL-backed task queue."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from cps.queue.db_queue import DbTaskQueue
from cps.queue.protocol import Task, TaskQueue


class TestDbTaskQueueConformance:
    def test_implements_task_queue_protocol(self):
        mock_session = AsyncMock()
        queue = DbTaskQueue(session=mock_session)
        assert isinstance(queue, TaskQueue)


class TestPopNext:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.flush = AsyncMock()
        session.get = AsyncMock()
        return session

    async def test_returns_none_when_no_pending_tasks(self, mock_session):
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        queue = DbTaskQueue(session=mock_session)
        task = await queue.pop_next("amazon")
        assert task is None

    async def test_returns_task_when_pending_exists(self, mock_session):
        # Mock CrawlTask ORM object
        crawl_task = MagicMock()
        crawl_task.id = 42
        crawl_task.product_id = 100
        crawl_task.platform = "amazon"
        crawl_task.status = "pending"
        crawl_task.started_at = None

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = crawl_task
        mock_session.execute.return_value = mock_result

        # Mock Product lookup
        mock_product = MagicMock()
        mock_product.platform_id = "B08N5WRWNW"
        mock_session.get.return_value = mock_product

        queue = DbTaskQueue(session=mock_session)
        task = await queue.pop_next("amazon")

        assert isinstance(task, Task)
        assert task.id == 42
        assert task.product_id == 100
        assert task.platform_id == "B08N5WRWNW"

    async def test_marks_task_in_progress(self, mock_session):
        crawl_task = MagicMock()
        crawl_task.id = 42
        crawl_task.product_id = 100
        crawl_task.platform = "amazon"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = crawl_task
        mock_session.execute.return_value = mock_result

        mock_product = MagicMock()
        mock_product.platform_id = "B08N5WRWNW"
        mock_session.get.return_value = mock_product

        queue = DbTaskQueue(session=mock_session)
        await queue.pop_next("amazon")

        assert crawl_task.status == "in_progress"
        assert crawl_task.started_at is not None

    async def test_returns_none_when_product_not_found(self, mock_session):
        crawl_task = MagicMock()
        crawl_task.id = 42
        crawl_task.product_id = 999

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = crawl_task
        mock_session.execute.return_value = mock_result
        mock_session.get.return_value = None  # product not found

        queue = DbTaskQueue(session=mock_session)
        task = await queue.pop_next("amazon")
        assert task is None
        assert crawl_task.status == "failed"


class TestComplete:
    async def test_marks_completed_with_next_crawl(self):
        mock_session = AsyncMock()
        crawl_task = MagicMock()
        crawl_task.total_crawls = 5
        mock_session.get.return_value = crawl_task

        queue = DbTaskQueue(session=mock_session)
        await queue.complete(42)

        assert crawl_task.status == "completed"
        assert crawl_task.completed_at is not None
        assert crawl_task.total_crawls == 6
        assert crawl_task.next_crawl_at is not None
        assert crawl_task.error_message is None

    async def test_noop_when_task_not_found(self):
        mock_session = AsyncMock()
        mock_session.get.return_value = None

        queue = DbTaskQueue(session=mock_session)
        await queue.complete(999)  # should not raise


class TestFail:
    async def test_increments_retry_and_requeues_when_under_max(self):
        mock_session = AsyncMock()
        crawl_task = MagicMock()
        crawl_task.retry_count = 1
        crawl_task.max_retries = 3
        mock_session.get.return_value = crawl_task

        queue = DbTaskQueue(session=mock_session)
        await queue.fail(42, "Server error (500)")

        assert crawl_task.retry_count == 2
        assert crawl_task.status == "pending"
        assert crawl_task.error_message == "Server error (500)"

    async def test_marks_failed_when_max_retries_reached(self):
        mock_session = AsyncMock()
        crawl_task = MagicMock()
        crawl_task.retry_count = 2
        crawl_task.max_retries = 3
        mock_session.get.return_value = crawl_task

        queue = DbTaskQueue(session=mock_session)
        await queue.fail(42, "Server error (500)")

        assert crawl_task.retry_count == 3
        assert crawl_task.status == "failed"


class TestRequeue:
    async def test_resets_to_pending_without_retry_increment(self):
        mock_session = AsyncMock()
        crawl_task = MagicMock()
        crawl_task.retry_count = 1
        crawl_task.status = "in_progress"
        mock_session.get.return_value = crawl_task

        queue = DbTaskQueue(session=mock_session)
        await queue.requeue(42)

        assert crawl_task.status == "pending"
        assert crawl_task.started_at is None
        assert crawl_task.error_message is None
        assert crawl_task.retry_count == 1  # not incremented
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_db_queue.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.queue.db_queue'`

- [ ] **Step 3: Write implementation**

```python
# src/cps/queue/db_queue.py
"""PostgreSQL-backed task queue using SELECT FOR UPDATE SKIP LOCKED.

Enables safe concurrent access — multiple workers can pull from the
same queue without duplicate processing. SKIP LOCKED is non-blocking:
if a row is locked by another worker, it's simply skipped.
"""

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import CrawlTask, Product
from cps.queue.protocol import Task

log = structlog.get_logger()


class DbTaskQueue:
    """Task queue backed by the crawl_tasks PostgreSQL table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def pop_next(self, platform: str) -> Task | None:
        """Atomically claim the next pending task for the given platform.

        Uses FOR UPDATE SKIP LOCKED to prevent duplicate processing
        across concurrent workers.
        """
        stmt = (
            select(CrawlTask)
            .where(CrawlTask.status == "pending", CrawlTask.platform == platform)
            .order_by(CrawlTask.priority, CrawlTask.scheduled_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        crawl_task = result.scalar_one_or_none()

        if crawl_task is None:
            return None

        crawl_task.status = "in_progress"
        crawl_task.started_at = datetime.now(timezone.utc)
        await self._session.flush()

        product = await self._session.get(Product, crawl_task.product_id)
        if product is None:
            crawl_task.status = "failed"
            crawl_task.error_message = "Product not found"
            await self._session.flush()
            log.error("product_not_found", task_id=crawl_task.id, product_id=crawl_task.product_id)
            return None

        return Task(
            id=crawl_task.id,
            product_id=crawl_task.product_id,
            platform_id=product.platform_id,
            platform=crawl_task.platform,
        )

    async def complete(self, task_id: int) -> None:
        """Mark a task as completed and schedule the next crawl (7 days)."""
        task = await self._session.get(CrawlTask, task_id)
        if task is None:
            return
        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        task.total_crawls += 1
        task.next_crawl_at = datetime.now(timezone.utc) + timedelta(days=7)
        task.error_message = None
        await self._session.flush()

    async def fail(self, task_id: int, error: str) -> None:
        """Mark a task as failed with retry logic.

        Increments retry_count. If max_retries reached, status = 'failed'.
        Otherwise, status = 'pending' for automatic retry.
        """
        task = await self._session.get(CrawlTask, task_id)
        if task is None:
            return
        task.retry_count += 1
        task.error_message = error
        if task.retry_count >= task.max_retries:
            task.status = "failed"
        else:
            task.status = "pending"
        await self._session.flush()

    async def requeue(self, task_id: int) -> None:
        """Return a task to pending without incrementing retry count.

        Used for transient errors like rate limiting (429) where the
        task should be retried without penalty.
        """
        task = await self._session.get(CrawlTask, task_id)
        if task is None:
            return
        task.status = "pending"
        task.started_at = None
        task.error_message = None
        await self._session.flush()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_db_queue.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/queue/db_queue.py tests/unit/test_db_queue.py
git commit -m "feat: add DbTaskQueue with SELECT FOR UPDATE SKIP LOCKED"
```

---

### Task 7: Result Store

**Files:**
- Create: `src/cps/pipeline/result_store.py`
- Modify: `tests/unit/test_orchestrator_upsert.py` (update import)
- Test: `tests/unit/test_result_store.py`

Extract `_build_price_summary_upsert` from `orchestrator.py` and add `store_results()`.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_result_store.py
"""Tests for result_store — FetchRun creation, PriceHistory insert, PriceSummary upsert."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.pipeline.result_store import _build_price_summary_upsert, store_results
from cps.platforms.protocol import ParseResult, PriceRecord, PriceSummaryData


class TestBuildPriceSummaryUpsert:
    def test_generates_on_conflict_sql(self):
        from sqlalchemy.dialects import postgresql

        stmt = _build_price_summary_upsert(
            product_id=1,
            price_type="amazon",
            lowest_price=16900,
            lowest_date=None,
            highest_price=24900,
            highest_date=None,
            current_price=18900,
            current_date=None,
            extraction_id=1,
        )
        compiled = str(stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        ))
        assert "ON CONFLICT" in compiled.upper() or "on conflict" in compiled.lower()


class TestStoreResults:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()
        session.begin_nested = MagicMock()
        return session

    async def test_creates_fetch_run(self, mock_session):
        parse_result = ParseResult(
            records=[],
            points_extracted=0,
            confidence=0.5,
            validation_passed=False,
            validation_status="failed",
        )

        # Mock flush to set run.id
        async def set_id():
            for call in mock_session.add.call_args_list:
                obj = call[0][0]
                if hasattr(obj, "product_id") and hasattr(obj, "chart_path"):
                    obj.id = 1
        mock_session.flush.side_effect = set_id

        run_id = await store_results(mock_session, product_id=42, parse_result=parse_result)
        assert mock_session.add.called

    async def test_stores_price_records(self, mock_session):
        records = [
            PriceRecord("amazon", date(2025, 1, 1), 29900, "ccc_chart"),
            PriceRecord("amazon", date(2025, 2, 1), 24900, "ccc_chart"),
        ]
        parse_result = ParseResult(
            records=records,
            points_extracted=2,
            validation_status="success",
        )

        # Mock nested context manager for savepoint
        nested_cm = AsyncMock()
        nested_cm.__aenter__ = AsyncMock()
        nested_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session.begin_nested.return_value = nested_cm

        async def set_id():
            for call in mock_session.add.call_args_list:
                obj = call[0][0]
                if hasattr(obj, "chart_path"):
                    obj.id = 1
        mock_session.flush.side_effect = set_id

        await store_results(mock_session, product_id=42, parse_result=parse_result)
        # Should have added FetchRun + 2 PriceHistory = at least 3 adds
        assert mock_session.add.call_count >= 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_result_store.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.pipeline.result_store'`

- [ ] **Step 3: Write implementation**

```python
# src/cps/pipeline/result_store.py
"""Result storage — persists parse results to FetchRun, PriceHistory, PriceSummary.

Extracted from orchestrator.py to enable reuse by both PipelineOrchestrator
and the Worker entry point.
"""

from datetime import date

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import FetchRun, PriceHistory, PriceSummary
from cps.platforms.protocol import ParseResult


def _build_price_summary_upsert(
    product_id: int,
    price_type: str,
    lowest_price: int | None,
    lowest_date: date | None,
    highest_price: int | None,
    highest_date: date | None,
    current_price: int | None,
    current_date: date | None,
    extraction_id: int | None,
    source: str = "ccc_chart",
) -> object:
    """Build PostgreSQL INSERT ... ON CONFLICT DO UPDATE for PriceSummary."""
    stmt = pg_insert(PriceSummary).values(
        product_id=product_id,
        price_type=price_type,
        lowest_price=lowest_price,
        lowest_date=lowest_date,
        highest_price=highest_price,
        highest_date=highest_date,
        current_price=current_price,
        current_date=current_date,
        extraction_id=extraction_id,
        source=source,
    )
    return stmt.on_conflict_do_update(
        index_elements=["product_id", "price_type"],
        set_={
            "lowest_price": stmt.excluded.lowest_price,
            "lowest_date": stmt.excluded.lowest_date,
            "highest_price": stmt.excluded.highest_price,
            "highest_date": stmt.excluded.highest_date,
            "current_price": stmt.excluded.current_price,
            "current_date": stmt.excluded.current_date,
            "extraction_id": stmt.excluded.extraction_id,
            "source": stmt.excluded.source,
            "updated_at": func.now(),
        },
    )


async def store_results(
    session: AsyncSession,
    product_id: int,
    parse_result: ParseResult,
    chart_path: str | None = None,
    platform: str = "amazon",
) -> int:
    """Persist parse results: create FetchRun, insert PriceHistory, upsert PriceSummary.

    Returns the FetchRun ID.
    """
    run = FetchRun(
        product_id=product_id,
        chart_path=chart_path,
        status=parse_result.validation_status,
        points_extracted=parse_result.points_extracted,
        ocr_confidence=parse_result.confidence,
        validation_passed=parse_result.validation_passed,
        platform=platform,
    )
    session.add(run)
    await session.flush()

    # Store price history (skip duplicates via savepoint)
    for record in parse_result.records:
        try:
            async with session.begin_nested():
                ph = PriceHistory(
                    product_id=product_id,
                    price_type=record.price_type,
                    recorded_date=record.recorded_date,
                    price_cents=record.price_cents,
                    extraction_id=run.id,
                    source=record.source,
                )
                session.add(ph)
        except Exception:
            pass  # duplicate — savepoint auto-rolled-back

    # Store price summaries (UPSERT — update on re-crawl)
    for summary in parse_result.summaries:
        stmt = _build_price_summary_upsert(
            product_id=product_id,
            price_type=summary.price_type,
            lowest_price=summary.lowest_price,
            lowest_date=summary.lowest_date,
            highest_price=summary.highest_price,
            highest_date=summary.highest_date,
            current_price=summary.current_price,
            current_date=summary.current_date,
            extraction_id=run.id,
        )
        await session.execute(stmt)

    return run.id
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_result_store.py -v
```
Expected: all PASS

- [ ] **Step 5: Update existing test import**

```python
# tests/unit/test_orchestrator_upsert.py — change line 3:
# OLD: from cps.pipeline.orchestrator import _build_price_summary_upsert
# NEW: from cps.pipeline.result_store import _build_price_summary_upsert
```

Run: `uv run pytest tests/unit/test_orchestrator_upsert.py -v` — should still PASS.

- [ ] **Step 6: Commit**

```bash
git add src/cps/pipeline/result_store.py tests/unit/test_result_store.py tests/unit/test_orchestrator_upsert.py
git commit -m "feat: extract result_store from orchestrator (FetchRun + PriceHistory + PriceSummary)"
```

---

### Task 8: Refactor PipelineOrchestrator

**Files:**
- Modify: `src/cps/pipeline/orchestrator.py`
- Modify: `src/cps/cli.py:134-167` (update crawl run constructor)

The orchestrator now accepts TaskQueue + Fetcher + Parser via constructor instead of building them internally. Task management delegated to TaskQueue. Data extraction delegated to Fetcher + Parser. Result storage delegated to `store_results`. Recovery state machine preserved.

- [ ] **Step 1: Rewrite orchestrator**

Replace `src/cps/pipeline/orchestrator.py` with:

```python
"""Pipeline orchestrator — batch processing with auto-recovery state machine."""

import asyncio
import enum
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.alerts.email import AlertService
from cps.crawler.downloader import (
    BlockedError,
    DownloadError,
    RateLimitError,
    ServerError,
)
from cps.db.models import CrawlTask
from cps.pipeline.result_store import store_results
from cps.platforms.protocol import PlatformFetcher, PlatformParser
from cps.queue.protocol import Task, TaskQueue

log = structlog.get_logger()


class RecoveryState(enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    RECOVERING_1 = "recovering_1"
    PAUSED_2 = "paused_2"
    RECOVERING_2 = "recovering_2"
    PAUSED_3 = "paused_3"
    RECOVERING_3 = "recovering_3"
    STOPPED = "stopped"


_RECOVERY_TRANSITIONS = {
    RecoveryState.PAUSED: (3600, RecoveryState.RECOVERING_1),
    RecoveryState.PAUSED_2: (21600, RecoveryState.RECOVERING_2),
    RecoveryState.PAUSED_3: (86400, RecoveryState.RECOVERING_3),
}

_FAILURE_TRANSITIONS = {
    RecoveryState.RUNNING: RecoveryState.PAUSED,
    RecoveryState.RECOVERING_1: RecoveryState.PAUSED_2,
    RecoveryState.RECOVERING_2: RecoveryState.PAUSED_3,
    RecoveryState.RECOVERING_3: RecoveryState.STOPPED,
}

CONSECUTIVE_FAILURE_THRESHOLD = 50


class PipelineOrchestrator:
    """Batch-process crawl tasks with auto-recovery.

    Uses protocol-based Fetcher/Parser for platform extensibility
    and TaskQueue for safe concurrent task consumption.
    """

    def __init__(
        self,
        session: AsyncSession,
        queue: TaskQueue,
        fetcher: PlatformFetcher,
        parser: PlatformParser,
        platform: str = "amazon",
        alert_service: AlertService | None = None,
    ) -> None:
        self._session = session
        self._queue = queue
        self._fetcher = fetcher
        self._parser = parser
        self._platform = platform
        self._alert_service = alert_service

        self._state = RecoveryState.RUNNING
        self._consecutive_failures = 0

    @property
    def state(self) -> RecoveryState:
        return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    async def run(self, limit: int = 10) -> dict:
        """Process up to `limit` pending crawl tasks.

        Pops tasks one at a time via TaskQueue (FOR UPDATE SKIP LOCKED).
        Returns summary dict with counts.
        """
        succeeded = 0
        failed = 0
        total = 0

        for _ in range(limit):
            if self._state == RecoveryState.STOPPED:
                log.warning("pipeline_stopped", processed=total)
                break

            if (
                self._state in _FAILURE_TRANSITIONS
                and self._consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD
            ):
                await self._transition_to_failure()
                if self._state == RecoveryState.STOPPED:
                    break
                wait_secs, next_state = _RECOVERY_TRANSITIONS[self._state]
                log.info("recovery_waiting", state=self._state.value, wait_secs=wait_secs)
                await asyncio.sleep(wait_secs)
                self._state = next_state
                self._consecutive_failures = 0
                log.info("recovery_resuming", state=self._state.value)

            task = await self._queue.pop_next(self._platform)
            if task is None:
                break

            total += 1
            success = await self._process_one(task)
            await self._session.commit()

            if success:
                succeeded += 1
                self._consecutive_failures = 0
                if self._state != RecoveryState.RUNNING:
                    self._state = RecoveryState.RUNNING
                    log.info("recovery_success", msg="Back to full speed")
            else:
                failed += 1
                self._consecutive_failures += 1

        return {"succeeded": succeeded, "failed": failed, "total": total}

    async def _process_one(self, task: Task) -> bool:
        """Process a single crawl task. Returns True on success."""
        try:
            fetch_result = await self._fetcher.fetch(task.platform_id)
            parse_result = self._parser.parse(fetch_result)

            await store_results(
                self._session,
                task.product_id,
                parse_result,
                chart_path=fetch_result.storage_path,
                platform=task.platform,
            )

            await self._queue.complete(task.id)
            log.info(
                "crawl_success",
                platform_id=task.platform_id,
                points=parse_result.points_extracted,
            )
            return True

        except RateLimitError:
            await self._queue.requeue(task.id)
            log.warning("rate_limited", platform_id=task.platform_id)
            return False

        except BlockedError:
            await self._queue.fail(task.id, "Blocked (403)")
            log.error("blocked", platform_id=task.platform_id)
            return False

        except (ServerError, DownloadError) as exc:
            await self._queue.fail(task.id, str(exc))
            log.error("download_error", platform_id=task.platform_id, error=str(exc))
            return False

        except Exception as exc:
            await self._queue.fail(task.id, str(exc))
            log.error("unexpected_error", platform_id=task.platform_id, error=str(exc))
            return False

    async def _transition_to_failure(self) -> None:
        """Transition to the next failure state."""
        next_state = _FAILURE_TRANSITIONS.get(self._state)
        if next_state is None:
            return

        old_state = self._state
        self._state = next_state
        self._consecutive_failures = 0

        log.warning(
            "state_transition",
            from_state=old_state.value,
            to_state=next_state.value,
        )

        if self._alert_service:
            severity = "CRITICAL" if next_state == RecoveryState.STOPPED else "WARNING"
            await self._alert_service.send_alert(
                severity=severity,
                title=f"Pipeline {next_state.value}",
                body=f"Auto-recovery: {old_state.value} → {next_state.value}. "
                f"Consecutive failures reached threshold.",
            )

    @staticmethod
    async def recover_stale_tasks(
        session: AsyncSession,
        stale_threshold_hours: int = 1,
    ) -> int:
        """Reset stale in_progress tasks to pending (crash recovery).

        Returns the number of tasks reset.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_threshold_hours)

        result = await session.execute(
            select(CrawlTask).where(
                CrawlTask.status == "in_progress",
                CrawlTask.started_at < cutoff,
            )
        )
        stale_tasks = list(result.scalars().all())

        for task in stale_tasks:
            task.status = "pending"
            task.started_at = None
            log.info(
                "stale_task_reset",
                task_id=task.id,
                retry_count=task.retry_count,
            )

        if stale_tasks:
            await session.flush()
            log.info("crash_recovery_complete", count=len(stale_tasks))

        return len(stale_tasks)
```

- [ ] **Step 2: Update CLI `crawl run` command**

In `src/cps/cli.py`, update the `crawl_run` function (lines 134-167):

```python
@crawl_app.command("run")
def crawl_run(
    limit: int = typer.Option(10, "--limit", "-n", help="Max products to crawl"),
) -> None:
    """Crawl next N pending products."""
    settings = get_settings()
    _configure_logging(settings.log_level, settings.log_format)

    async def _do():
        from cps.db.session import create_session_factory
        from cps.pipeline.orchestrator import PipelineOrchestrator
        from cps.platforms.registry import get_fetcher, get_parser
        from cps.queue.db_queue import DbTaskQueue

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            # Crash recovery first
            recovered = await PipelineOrchestrator.recover_stale_tasks(session)
            if recovered:
                typer.echo(f"Recovered {recovered} stale tasks")

            queue = DbTaskQueue(session)
            fetcher = get_fetcher(
                "amazon",
                base_url=settings.ccc_base_url,
                data_dir=settings.data_dir,
                rate_limit=settings.ccc_rate_limit,
            )
            parser = get_parser("amazon")

            orchestrator = PipelineOrchestrator(
                session=session,
                queue=queue,
                fetcher=fetcher,
                parser=parser,
                platform="amazon",
            )
            summary = await orchestrator.run(limit=limit)
            await session.commit()

        typer.echo(
            f"Crawl complete: {summary['succeeded']} succeeded, "
            f"{summary['failed']} failed, {summary['total']} total"
        )

    _run_async(_do())
```

- [ ] **Step 3: Run all existing tests**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: Check for failures from the refactor. The integration tests for pipeline, auto_recovery, and crash_recovery may need updates — see Task 9.

- [ ] **Step 4: Commit**

```bash
git add src/cps/pipeline/orchestrator.py src/cps/cli.py
git commit -m "refactor: PipelineOrchestrator uses TaskQueue + Fetcher + Parser protocols"
```

---

### Task 9: Fix Existing Test Breakage

**Files:**
- Modify: `tests/integration/test_pipeline.py` (update orchestrator construction)
- Modify: `tests/integration/test_auto_recovery.py` (update orchestrator construction)
- Modify: `tests/integration/test_crash_recovery.py` (if affected)

The PipelineOrchestrator constructor changed: it now requires `queue`, `fetcher`, `parser` instead of `data_dir`, `base_url`, `rate_limit`. Integration tests that construct PipelineOrchestrator directly need updating.

- [ ] **Step 1: Run existing tests and identify failures**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | grep -E "FAILED|ERROR"
```

- [ ] **Step 2: Fix each failing test**

For integration tests that construct PipelineOrchestrator:

```python
# Common pattern for tests that create orchestrator:
from cps.platforms.amazon.fetcher import AmazonFetcher
from cps.platforms.amazon.parser import AmazonParser
from cps.queue.db_queue import DbTaskQueue

# OLD:
# orchestrator = PipelineOrchestrator(
#     session=session,
#     data_dir=data_dir,
#     base_url=base_url,
#     rate_limit=10.0,
# )

# NEW:
queue = DbTaskQueue(session)
fetcher = AmazonFetcher(base_url=base_url, data_dir=data_dir, rate_limit=10.0)
parser = AmazonParser()
orchestrator = PipelineOrchestrator(
    session=session,
    queue=queue,
    fetcher=fetcher,
    parser=parser,
    platform="amazon",
)
```

Read each failing test file, understand its specific setup, and apply the minimal changes needed to restore green status. Key consideration: some tests mock internal methods of the orchestrator (e.g., `_process_one`). These may need adjustment since `_process_one` now takes a `Task` (from queue protocol) instead of a `CrawlTask` (ORM model).

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short
```
Expected: All previously-passing tests pass again. Pre-existing failures (7 integration tests noted in session 13 handoff) may still fail.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "fix: update integration tests for refactored PipelineOrchestrator"
```

---

### Task 10: Discovery Validation Pipeline

**Files:**
- Create: `src/cps/discovery/__init__.py`
- Create: `src/cps/discovery/pipeline.py`
- Test: `tests/unit/test_discovery_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_discovery_pipeline.py
"""Tests for ASIN discovery validation pipeline."""

import re
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.discovery.pipeline import DiscoveryPipeline, SubmitResult, validate_platform_id


class TestValidatePlatformId:
    def test_valid_amazon_asin(self):
        assert validate_platform_id("B08N5WRWNW", "amazon") is True

    def test_invalid_amazon_asin_too_short(self):
        assert validate_platform_id("B08N", "amazon") is False

    def test_invalid_amazon_asin_special_chars(self):
        assert validate_platform_id("B08N-WRW!W", "amazon") is False

    def test_unknown_platform_raises(self):
        with pytest.raises(ValueError, match="Unknown platform"):
            validate_platform_id("12345", "ebay")


class TestSubmitResult:
    def test_dataclass_fields(self):
        result = SubmitResult(submitted=10, skipped=3, total=13)
        assert result.submitted == 10
        assert result.skipped == 3


class TestSubmitCandidates:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()
        return session

    async def test_creates_products_and_tasks(self, mock_session):
        # No existing products
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        pipeline = DiscoveryPipeline(mock_session)
        result = await pipeline.submit_candidates(
            ["B08N5WRWNW", "B09V3KXJPB"],
            platform="amazon",
        )

        assert result.submitted == 2
        assert result.skipped == 0
        assert result.total == 2

    async def test_skips_existing_products(self, mock_session):
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = ["B08N5WRWNW"]
        mock_session.execute.return_value = mock_result

        pipeline = DiscoveryPipeline(mock_session)
        result = await pipeline.submit_candidates(
            ["B08N5WRWNW", "B09V3KXJPB"],
            platform="amazon",
        )

        assert result.submitted == 1
        assert result.skipped == 1

    async def test_skips_invalid_platform_ids(self, mock_session):
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        pipeline = DiscoveryPipeline(mock_session)
        result = await pipeline.submit_candidates(
            ["B08N5WRWNW", "INVALID", "B09V3KXJPB"],
            platform="amazon",
        )

        assert result.submitted == 2
        assert result.skipped == 1

    async def test_uses_high_priority_for_validation(self, mock_session):
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        pipeline = DiscoveryPipeline(mock_session)
        await pipeline.submit_candidates(
            ["B08N5WRWNW"],
            platform="amazon",
            priority=2,
        )

        # Verify CrawlTask was created (via session.add calls)
        assert mock_session.add.call_count >= 2  # Product + CrawlTask


class TestDeactivateNoDataProducts:
    async def test_deactivates_products_with_zero_points(self):
        mock_session = AsyncMock()

        # Mock: find products with completed tasks but 0 points
        mock_product = MagicMock()
        mock_product.is_active = True

        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [mock_product]
        mock_session.execute.return_value = mock_result

        pipeline = DiscoveryPipeline(mock_session)
        count = await pipeline.deactivate_no_data_products()

        assert count == 1
        assert mock_product.is_active is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_discovery_pipeline.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.discovery'`

- [ ] **Step 3: Write implementation**

```python
# src/cps/discovery/__init__.py
"""Product discovery and validation pipeline."""
```

```python
# src/cps/discovery/pipeline.py
"""ASIN discovery validation pipeline.

Handles candidate submission (create Product + high-priority CrawlTask)
and post-crawl validation (deactivate products with no price data).
"""

import re
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import CrawlTask, FetchRun, Product

log = structlog.get_logger()

_PLATFORM_VALIDATORS = {
    "amazon": re.compile(r"^[A-Z0-9]{10}$"),
}


def validate_platform_id(platform_id: str, platform: str) -> bool:
    """Validate a platform_id against platform-specific rules.

    Raises:
        ValueError: If platform is unknown.
    """
    pattern = _PLATFORM_VALIDATORS.get(platform)
    if pattern is None:
        raise ValueError(f"Unknown platform: {platform}")
    return bool(pattern.match(platform_id))


@dataclass
class SubmitResult:
    """Summary of candidate submission."""

    submitted: int
    skipped: int
    total: int


class DiscoveryPipeline:
    """Manages product discovery: submit candidates and validate via crawl."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def submit_candidates(
        self,
        platform_ids: list[str],
        platform: str = "amazon",
        priority: int = 2,
    ) -> SubmitResult:
        """Import candidate platform_ids for validation crawling.

        Creates Product + CrawlTask for each valid, non-existing ID.
        Uses higher priority (default 2) so validation runs before routine crawls.
        """
        total = len(platform_ids)
        skipped = 0

        # Filter valid IDs
        valid_ids: list[str] = []
        for pid in platform_ids:
            if validate_platform_id(pid, platform):
                valid_ids.append(pid)
            else:
                skipped += 1
                log.debug("invalid_platform_id", platform_id=pid, platform=platform)

        # Deduplicate
        unique_ids = list(dict.fromkeys(valid_ids))
        skipped += len(valid_ids) - len(unique_ids)

        # Check existing
        if unique_ids:
            result = await self._session.execute(
                select(Product.platform_id).where(
                    Product.platform == platform,
                    Product.platform_id.in_(unique_ids),
                )
            )
            existing = set(result.scalars().all())
        else:
            existing = set()

        submitted = 0
        for pid in unique_ids:
            if pid in existing:
                skipped += 1
                continue

            product = Product(platform_id=pid, platform=platform)
            self._session.add(product)
            await self._session.flush()

            task = CrawlTask(
                product_id=product.id,
                platform=platform,
                priority=priority,
                status="pending",
            )
            self._session.add(task)
            submitted += 1

        await self._session.flush()

        log.info(
            "discovery_submitted",
            platform=platform,
            submitted=submitted,
            skipped=skipped,
            total=total,
        )

        return SubmitResult(submitted=submitted, skipped=skipped, total=total)

    async def deactivate_no_data_products(self, platform: str = "amazon") -> int:
        """Deactivate products whose latest FetchRun has 0 points extracted.

        These are products where the CCC chart exists but contains no price data.
        Returns the count of deactivated products.
        """
        # Find active products with completed CrawlTasks where all FetchRuns have 0 points
        stmt = (
            select(Product)
            .join(CrawlTask, CrawlTask.product_id == Product.id)
            .join(FetchRun, FetchRun.product_id == Product.id)
            .where(
                Product.platform == platform,
                Product.is_active == True,  # noqa: E712
                CrawlTask.status == "completed",
                FetchRun.points_extracted == 0,
            )
        )
        result = await self._session.execute(stmt)
        products = list(result.scalars().all())

        for product in products:
            product.is_active = False
            log.info("product_deactivated", platform_id=product.platform_id, reason="no_data")

        if products:
            await self._session.flush()

        return len(products)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_discovery_pipeline.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/discovery/__init__.py src/cps/discovery/pipeline.py tests/unit/test_discovery_pipeline.py
git commit -m "feat: add discovery validation pipeline (candidate submission + no-data deactivation)"
```

---

### Task 11: Worker Entry Point + CLI Command

**Files:**
- Create: `src/cps/worker.py`
- Modify: `src/cps/cli.py` (add worker command group)
- Test: `tests/unit/test_worker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_worker.py
"""Tests for the generic worker loop."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.queue.protocol import Task
from cps.worker import WorkerLoop


class TestWorkerLoop:
    @pytest.fixture
    def mock_queue(self):
        queue = AsyncMock()
        queue.pop_next = AsyncMock(return_value=None)
        queue.complete = AsyncMock()
        queue.fail = AsyncMock()
        queue.requeue = AsyncMock()
        return queue

    @pytest.fixture
    def mock_fetcher(self):
        fetcher = AsyncMock()
        return fetcher

    @pytest.fixture
    def mock_parser(self):
        parser = MagicMock()
        return parser

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    def test_creates_worker_loop(self, mock_session, mock_queue, mock_fetcher, mock_parser):
        worker = WorkerLoop(
            session=mock_session,
            queue=mock_queue,
            fetcher=mock_fetcher,
            parser=mock_parser,
            platform="amazon",
        )
        assert worker is not None

    async def test_stops_when_no_tasks(self, mock_session, mock_queue, mock_fetcher, mock_parser):
        """Worker should sleep when no tasks, not crash."""
        mock_queue.pop_next.return_value = None

        worker = WorkerLoop(
            session=mock_session,
            queue=mock_queue,
            fetcher=mock_fetcher,
            parser=mock_parser,
            platform="amazon",
        )

        # Run with max_iterations=1 to avoid infinite loop
        result = await worker.run_once()
        assert result is False  # no task processed

    async def test_processes_task_successfully(self, mock_session, mock_queue, mock_fetcher, mock_parser):
        task = Task(id=1, product_id=42, platform_id="B08N5WRWNW", platform="amazon")
        mock_queue.pop_next.return_value = task

        from cps.platforms.protocol import FetchResult, ParseResult

        mock_fetcher.fetch.return_value = FetchResult(raw_data=b"png", storage_path="/tmp/x.png")
        mock_parser.parse.return_value = ParseResult(records=[], points_extracted=0)

        worker = WorkerLoop(
            session=mock_session,
            queue=mock_queue,
            fetcher=mock_fetcher,
            parser=mock_parser,
            platform="amazon",
        )

        with patch("cps.worker.store_results", new_callable=AsyncMock, return_value=1):
            result = await worker.run_once()

        assert result is True
        mock_queue.complete.assert_awaited_once_with(1)

    async def test_handles_download_error(self, mock_session, mock_queue, mock_fetcher, mock_parser):
        from cps.crawler.downloader import DownloadError

        task = Task(id=1, product_id=42, platform_id="B08N5WRWNW", platform="amazon")
        mock_queue.pop_next.return_value = task
        mock_fetcher.fetch.side_effect = DownloadError("timeout")

        worker = WorkerLoop(
            session=mock_session,
            queue=mock_queue,
            fetcher=mock_fetcher,
            parser=mock_parser,
            platform="amazon",
        )

        result = await worker.run_once()
        assert result is False
        mock_queue.fail.assert_awaited_once_with(1, "timeout")

    async def test_handles_rate_limit(self, mock_session, mock_queue, mock_fetcher, mock_parser):
        from cps.crawler.downloader import RateLimitError

        task = Task(id=1, product_id=42, platform_id="B08N5WRWNW", platform="amazon")
        mock_queue.pop_next.return_value = task
        mock_fetcher.fetch.side_effect = RateLimitError("429")

        worker = WorkerLoop(
            session=mock_session,
            queue=mock_queue,
            fetcher=mock_fetcher,
            parser=mock_parser,
            platform="amazon",
        )

        result = await worker.run_once()
        assert result is False
        mock_queue.requeue.assert_awaited_once_with(1)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/test_worker.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.worker'` or `ImportError`

- [ ] **Step 3: Write implementation**

```python
# src/cps/worker.py
"""Generic worker loop for continuous crawl processing.

Usage:
    python -m cps.worker --platform amazon
    cps worker run --platform amazon
"""

import asyncio
import signal

import structlog

from cps.crawler.downloader import (
    BlockedError,
    DownloadError,
    RateLimitError,
    ServerError,
)
from cps.pipeline.result_store import store_results
from cps.platforms.protocol import PlatformFetcher, PlatformParser
from cps.queue.protocol import TaskQueue

log = structlog.get_logger()


class WorkerLoop:
    """Continuously processes crawl tasks for a single platform."""

    def __init__(
        self,
        session: object,
        queue: TaskQueue,
        fetcher: PlatformFetcher,
        parser: PlatformParser,
        platform: str,
        idle_sleep: float = 5.0,
    ) -> None:
        self._session = session
        self._queue = queue
        self._fetcher = fetcher
        self._parser = parser
        self._platform = platform
        self._idle_sleep = idle_sleep
        self._running = True

    def stop(self) -> None:
        """Signal the worker to stop after the current task."""
        self._running = False

    async def run_once(self) -> bool:
        """Process a single task. Returns True if a task was successfully processed."""
        task = await self._queue.pop_next(self._platform)
        if task is None:
            return False

        try:
            fetch_result = await self._fetcher.fetch(task.platform_id)
            parse_result = self._parser.parse(fetch_result)

            await store_results(
                self._session,
                task.product_id,
                parse_result,
                chart_path=fetch_result.storage_path,
                platform=task.platform,
            )

            await self._queue.complete(task.id)
            await self._session.commit()
            log.info(
                "task_complete",
                platform_id=task.platform_id,
                points=parse_result.points_extracted,
            )
            return True

        except RateLimitError:
            await self._queue.requeue(task.id)
            await self._session.commit()
            log.warning("rate_limited", platform_id=task.platform_id)
            return False

        except BlockedError:
            await self._queue.fail(task.id, "Blocked (403)")
            await self._session.commit()
            log.error("blocked", platform_id=task.platform_id)
            return False

        except (ServerError, DownloadError) as exc:
            await self._queue.fail(task.id, str(exc))
            await self._session.commit()
            log.error("download_error", platform_id=task.platform_id, error=str(exc))
            return False

        except Exception as exc:
            await self._queue.fail(task.id, str(exc))
            await self._session.commit()
            log.error("unexpected_error", platform_id=task.platform_id, error=str(exc))
            return False

    async def run_forever(self) -> None:
        """Main loop — process tasks until stopped."""
        log.info("worker_started", platform=self._platform)

        while self._running:
            processed = await self.run_once()
            if not processed:
                await asyncio.sleep(self._idle_sleep)

        log.info("worker_stopped", platform=self._platform)
```

- [ ] **Step 4: Add CLI worker command**

In `src/cps/cli.py`, add after the `bot_app` definition (around line 25):

```python
worker_app = typer.Typer(help="Worker operations")
app.add_typer(worker_app, name="worker")
```

And add the worker run command (before `if __name__ == "__main__":`):

```python
@worker_app.command("run")
def worker_run(
    platform: str = typer.Option("amazon", "--platform", "-p", help="Platform to process"),
) -> None:
    """Start a continuous worker for the given platform."""
    import signal

    settings = get_settings()
    _configure_logging(settings.log_level, settings.log_format)

    async def _do():
        from cps.db.session import create_session_factory
        from cps.pipeline.orchestrator import PipelineOrchestrator
        from cps.platforms.registry import get_fetcher, get_parser
        from cps.queue.db_queue import DbTaskQueue
        from cps.worker import WorkerLoop

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            # Crash recovery first
            recovered = await PipelineOrchestrator.recover_stale_tasks(session)
            if recovered:
                typer.echo(f"Recovered {recovered} stale tasks")
                await session.commit()

            queue = DbTaskQueue(session)
            fetcher = get_fetcher(
                platform,
                base_url=settings.ccc_base_url,
                data_dir=settings.data_dir,
                rate_limit=settings.ccc_rate_limit,
            )
            parser = get_parser(platform)

            worker = WorkerLoop(
                session=session,
                queue=queue,
                fetcher=fetcher,
                parser=parser,
                platform=platform,
            )

            # Graceful shutdown on SIGINT/SIGTERM
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, worker.stop)

            typer.echo(f"Worker started for platform={platform}")
            await worker.run_forever()

    _run_async(_do())
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/test_worker.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/cps/worker.py src/cps/cli.py tests/unit/test_worker.py
git commit -m "feat: add worker loop + CLI command for continuous crawl processing"
```

---

### Task 12: Full Verification

**Files:** None (verification only)

- [ ] **Step 1: Run complete test suite**

```bash
uv run pytest tests/ -v --tb=short
```
Expected: All unit tests pass. Pre-existing integration test failures (7 from session 13) may still fail — these are NOT introduced by Phase 1B.

- [ ] **Step 2: Check coverage**

```bash
uv run pytest tests/ --cov=cps --cov-report=term-missing
```
Expected: ≥ 80% overall coverage. New files should have good coverage from their unit tests.

- [ ] **Step 3: Verify imports are clean**

```bash
uv run python -c "
from cps.platforms.protocol import PlatformFetcher, PlatformParser, PriceRecord, FetchResult, ParseResult, PriceSummaryData
from cps.platforms.registry import get_fetcher, get_parser
from cps.platforms.amazon.fetcher import AmazonFetcher
from cps.platforms.amazon.parser import AmazonParser
from cps.queue.protocol import Task, TaskQueue
from cps.queue.db_queue import DbTaskQueue
from cps.pipeline.result_store import store_results
from cps.discovery.pipeline import DiscoveryPipeline
from cps.worker import WorkerLoop
print('All imports OK')
"
```
Expected: `All imports OK`

- [ ] **Step 4: Commit final state if any fixes were needed**

```bash
git add -A
git status
# Only commit if there are changes
git commit -m "fix: final Phase 1B verification fixes"
```

---

## Summary

| Task | Component | New Tests | Key Abstraction |
|------|-----------|-----------|----------------|
| 1 | Platform types + protocols | ~10 | PriceRecord, FetchResult, ParseResult, PlatformFetcher, PlatformParser |
| 2 | AmazonFetcher | ~4 | Wraps CccDownloader + PngStorage |
| 3 | AmazonParser | ~7 | Wraps PixelAnalyzer + OcrReader + Validator |
| 4 | Platform registry | ~5 | get_fetcher() / get_parser() factory |
| 5 | Task + TaskQueue | ~3 | Task dataclass, TaskQueue Protocol |
| 6 | DbTaskQueue | ~8 | SELECT FOR UPDATE SKIP LOCKED |
| 7 | Result store | ~3 | store_results() extracted from orchestrator |
| 8 | Orchestrator refactor | 0 (existing) | Uses TaskQueue + Fetcher + Parser |
| 9 | Fix test breakage | 0 (fixes) | Integration test compatibility |
| 10 | Discovery pipeline | ~6 | submit_candidates + deactivate_no_data |
| 11 | Worker + CLI | ~5 | WorkerLoop.run_once / run_forever |
| 12 | Verification | 0 | Full suite + coverage + imports |

**Total new tests:** ~51
**Total files created:** 13 source + 9 test = 22
**Total files modified:** 3 source + ~3 test = ~6

**Gate:** `uv run pytest` green + ≥ 80% coverage before proceeding to Phase 2.
