"""Tests for PixelAnalyzer — T013.

Validates pixel-level curve detection on CCC chart images.
These tests are written TDD-style and MUST FAIL until implementation exists.
"""

from datetime import date
from pathlib import Path

import pytest

from cps.extractor.pixel_analyzer import PixelAnalyzer


@pytest.fixture
def analyzer() -> PixelAnalyzer:
    """Create a PixelAnalyzer instance."""
    return PixelAnalyzer()


class TestPixelAnalyzerNormalChart:
    """Tests using sample_chart_normal.png — standard 3-curve chart."""

    def test_detects_at_least_one_curve(
        self, analyzer: PixelAnalyzer, sample_chart_normal: Path
    ) -> None:
        """Analyzer should detect at least one price curve color in a normal chart."""
        result = analyzer.analyze(sample_chart_normal)

        # At least one price type should have data points
        detected_curves = {k: v for k, v in result.items() if len(v) > 0}
        assert len(detected_curves) >= 1, (
            f"Expected at least 1 detected curve, got {len(detected_curves)}"
        )

    def test_returns_date_price_tuples(
        self, analyzer: PixelAnalyzer, sample_chart_normal: Path
    ) -> None:
        """Each curve's data should be a list of (date, price_cents) tuples."""
        result = analyzer.analyze(sample_chart_normal)

        for price_type, data_points in result.items():
            if len(data_points) == 0:
                continue

            for point in data_points:
                assert isinstance(point, tuple), (
                    f"Expected tuple, got {type(point)} for {price_type}"
                )
                assert len(point) == 2, (
                    f"Expected 2-element tuple (date, price_cents), got {len(point)}"
                )

                point_date, price_cents = point
                assert isinstance(point_date, date), (
                    f"First element should be date, got {type(point_date)}"
                )
                assert isinstance(price_cents, int), (
                    f"Second element should be int (cents), got {type(price_cents)}"
                )

    def test_returns_valid_price_type_labels(
        self, analyzer: PixelAnalyzer, sample_chart_normal: Path
    ) -> None:
        """Result keys must be valid price_type labels: amazon, new, used."""
        result = analyzer.analyze(sample_chart_normal)

        valid_labels = {"amazon", "new", "used"}
        for key in result:
            assert key in valid_labels, (
                f"Unexpected price_type '{key}', expected one of {valid_labels}"
            )

    def test_dates_in_chronological_order(
        self, analyzer: PixelAnalyzer, sample_chart_normal: Path
    ) -> None:
        """Data points for each curve should be sorted by date ascending."""
        result = analyzer.analyze(sample_chart_normal)

        for price_type, data_points in result.items():
            if len(data_points) < 2:
                continue

            dates = [point[0] for point in data_points]
            for i in range(1, len(dates)):
                assert dates[i] >= dates[i - 1], (
                    f"Dates not chronological for '{price_type}': "
                    f"{dates[i - 1]} > {dates[i]} at index {i}"
                )


class TestPixelAnalyzerNoDataChart:
    """Tests using sample_chart_nodata.png — chart with no visible curves."""

    def test_handles_no_curves_gracefully(
        self, analyzer: PixelAnalyzer, sample_chart_nodata: Path
    ) -> None:
        """Analyzer should not crash on a chart with no data curves."""
        result = analyzer.analyze(sample_chart_nodata)

        assert isinstance(result, dict), (
            f"Expected dict, got {type(result)}"
        )

        # Either empty dict or dict with empty lists — both are acceptable
        for price_type, data_points in result.items():
            assert isinstance(data_points, list), (
                f"Expected list for '{price_type}', got {type(data_points)}"
            )

    def test_no_data_chart_has_no_points(
        self, analyzer: PixelAnalyzer, sample_chart_nodata: Path
    ) -> None:
        """A chart with no curves should yield zero total data points."""
        result = analyzer.analyze(sample_chart_nodata)

        total_points = sum(len(v) for v in result.values())
        assert total_points == 0, (
            f"Expected 0 data points for empty chart, got {total_points}"
        )


class TestPixelAnalyzerEdgeChart:
    """Tests using sample_chart_edge.png — chart with extreme price values."""

    def test_handles_high_prices(
        self, analyzer: PixelAnalyzer, sample_chart_edge: Path
    ) -> None:
        """Analyzer should handle very high price values (e.g. spike to ~$999)."""
        result = analyzer.analyze(sample_chart_edge)

        # Should detect at least one curve even with extreme values
        detected_curves = {k: v for k, v in result.items() if len(v) > 0}
        assert len(detected_curves) >= 1, (
            "Expected at least 1 detected curve in edge-case chart"
        )

    def test_edge_prices_are_reasonable(
        self, analyzer: PixelAnalyzer, sample_chart_edge: Path
    ) -> None:
        """Extracted prices should be non-negative and within Y-axis range ($0-$1000)."""
        result = analyzer.analyze(sample_chart_edge)

        for price_type, data_points in result.items():
            for point_date, price_cents in data_points:
                assert price_cents >= 0, (
                    f"Negative price {price_cents} for '{price_type}'"
                )
                # Y-axis is $0-$1000, so max is 100_000 cents
                assert price_cents <= 100_000, (
                    f"Price {price_cents} cents exceeds Y-axis max "
                    f"(100000 cents) for '{price_type}'"
                )

    def test_edge_chart_returns_valid_structure(
        self, analyzer: PixelAnalyzer, sample_chart_edge: Path
    ) -> None:
        """Edge chart result should have the same structure as normal charts."""
        result = analyzer.analyze(sample_chart_edge)

        assert isinstance(result, dict)
        valid_labels = {"amazon", "new", "used"}
        for key, value in result.items():
            assert key in valid_labels
            assert isinstance(value, list)
            for point in value:
                assert isinstance(point, tuple)
                assert len(point) == 2
