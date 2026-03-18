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
