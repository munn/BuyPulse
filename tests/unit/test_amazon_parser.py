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

    def test_builds_summaries_with_correct_dates(self, parser):
        """Summaries should use dates corresponding to actual min/max prices, not min/max dates."""
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
        assert amazon_summary.lowest_date == date(2025, 2, 1)   # date of lowest PRICE
        assert amazon_summary.highest_price == 29900
        assert amazon_summary.highest_date == date(2025, 1, 1)  # date of highest PRICE
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
