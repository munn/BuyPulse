"""Tests for OcrReader — T014.

Validates OCR text extraction from CCC chart images (axes labels, legend).
These tests are written TDD-style and MUST FAIL until implementation exists.
"""

from pathlib import Path

import pytest

from cps.extractor.ocr_reader import OcrReader, OcrResult


@pytest.fixture
def reader() -> OcrReader:
    """Create an OcrReader instance."""
    return OcrReader()


class TestOcrReaderNormalChart:
    """Tests using sample_chart_normal.png — standard readable chart."""

    def test_extracts_y_axis_labels(
        self, reader: OcrReader, sample_chart_normal: Path
    ) -> None:
        """Should extract at least 2 Y-axis price labels from a normal chart."""
        result = reader.read(sample_chart_normal)

        assert isinstance(result, OcrResult)
        assert len(result.y_axis_labels) >= 2, (
            f"Expected >= 2 Y-axis labels, got {len(result.y_axis_labels)}"
        )

    def test_y_axis_labels_are_pixel_price_tuples(
        self, reader: OcrReader, sample_chart_normal: Path
    ) -> None:
        """Y-axis labels should be (pixel_y, price_string) tuples."""
        result = reader.read(sample_chart_normal)

        for label in result.y_axis_labels:
            assert isinstance(label, tuple), (
                f"Expected tuple, got {type(label)}"
            )
            assert len(label) == 2

            pixel_y, price_string = label
            assert isinstance(pixel_y, int), (
                f"pixel_y should be int, got {type(pixel_y)}"
            )
            assert isinstance(price_string, str), (
                f"price_string should be str, got {type(price_string)}"
            )

    def test_extracts_x_axis_labels(
        self, reader: OcrReader, sample_chart_normal: Path
    ) -> None:
        """Should extract at least 2 X-axis date labels from a normal chart."""
        result = reader.read(sample_chart_normal)

        assert isinstance(result, OcrResult)
        assert len(result.x_axis_labels) >= 2, (
            f"Expected >= 2 X-axis labels, got {len(result.x_axis_labels)}"
        )

    def test_x_axis_labels_are_pixel_date_tuples(
        self, reader: OcrReader, sample_chart_normal: Path
    ) -> None:
        """X-axis labels should be (pixel_x, date_string) tuples."""
        result = reader.read(sample_chart_normal)

        for label in result.x_axis_labels:
            assert isinstance(label, tuple), (
                f"Expected tuple, got {type(label)}"
            )
            assert len(label) == 2

            pixel_x, date_string = label
            assert isinstance(pixel_x, int), (
                f"pixel_x should be int, got {type(pixel_x)}"
            )
            assert isinstance(date_string, str), (
                f"date_string should be str, got {type(date_string)}"
            )

    def test_extracts_legend_text(
        self, reader: OcrReader, sample_chart_normal: Path
    ) -> None:
        """Should extract legend entries with lowest/highest/current values."""
        result = reader.read(sample_chart_normal)

        assert isinstance(result.legend, dict), (
            f"Legend should be dict, got {type(result.legend)}"
        )

        # At least one price type should be present in legend
        assert len(result.legend) >= 1, (
            "Expected at least 1 legend entry"
        )

        valid_keys = {"amazon", "new", "used"}
        for price_type, values in result.legend.items():
            assert price_type in valid_keys, (
                f"Unexpected legend key '{price_type}'"
            )
            assert isinstance(values, dict), (
                f"Legend entry for '{price_type}' should be dict"
            )

    def test_legend_contains_price_fields(
        self, reader: OcrReader, sample_chart_normal: Path
    ) -> None:
        """Legend entries should contain lowest/highest/current price fields."""
        result = reader.read(sample_chart_normal)

        expected_fields = {"lowest", "lowest_date", "highest"}
        for price_type, values in result.legend.items():
            present_fields = set(values.keys())
            missing = expected_fields - present_fields
            assert len(missing) == 0, (
                f"Legend '{price_type}' missing fields: {missing}. "
                f"Has: {present_fields}"
            )

            # Price values should be strings or None
            for field_name, field_value in values.items():
                assert field_value is None or isinstance(field_value, str), (
                    f"Legend field '{field_name}' should be str or None, "
                    f"got {type(field_value)}"
                )

    def test_confidence_between_zero_and_one(
        self, reader: OcrReader, sample_chart_normal: Path
    ) -> None:
        """Confidence score should be a float between 0.0 and 1.0."""
        result = reader.read(sample_chart_normal)

        assert isinstance(result.confidence, float), (
            f"Confidence should be float, got {type(result.confidence)}"
        )
        assert 0.0 <= result.confidence <= 1.0, (
            f"Confidence {result.confidence} not in [0.0, 1.0]"
        )

    def test_normal_chart_has_reasonable_confidence(
        self, reader: OcrReader, sample_chart_normal: Path
    ) -> None:
        """A clear, normal chart should yield a confidence above 0.5."""
        result = reader.read(sample_chart_normal)

        assert result.confidence > 0.5, (
            f"Expected confidence > 0.5 for normal chart, got {result.confidence}"
        )


class TestOcrReaderNoDataChart:
    """Tests using sample_chart_nodata.png — chart with no/unreadable text."""

    def test_handles_unreadable_text_gracefully(
        self, reader: OcrReader, sample_chart_nodata: Path
    ) -> None:
        """Should not crash on a chart with no readable text."""
        result = reader.read(sample_chart_nodata)

        # Must return a valid OcrResult, not raise an exception
        assert isinstance(result, OcrResult)

    def test_low_confidence_for_unreadable_chart(
        self, reader: OcrReader, sample_chart_nodata: Path
    ) -> None:
        """An unreadable chart should produce low confidence."""
        result = reader.read(sample_chart_nodata)

        assert result.confidence < 0.5, (
            f"Expected confidence < 0.5 for unreadable chart, "
            f"got {result.confidence}"
        )

    def test_returns_valid_structure_for_nodata(
        self, reader: OcrReader, sample_chart_nodata: Path
    ) -> None:
        """Even with no data, the result structure should be valid."""
        result = reader.read(sample_chart_nodata)

        assert isinstance(result.y_axis_labels, list)
        assert isinstance(result.x_axis_labels, list)
        assert isinstance(result.legend, dict)
        assert isinstance(result.confidence, float)
