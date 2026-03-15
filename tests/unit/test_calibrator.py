"""Tests for Calibrator — T015.

Validates pixel-to-value mapping functions for chart axes.
These tests are written TDD-style and MUST FAIL until implementation exists.
"""

from datetime import date

import pytest

from cps.extractor.calibrator import Calibrator


@pytest.fixture
def calibrator() -> Calibrator:
    """Create a Calibrator instance."""
    return Calibrator()


class TestBuildPriceMapping:
    """Tests for Calibrator.build_price_mapping (pixel_y -> price_cents)."""

    def test_maps_known_points_exactly(self, calibrator: Calibrator) -> None:
        """Mapping should return exact values for known calibration points."""
        # pixel_y=100 -> $100.00 (10000 cents), pixel_y=500 -> $0.00 (0 cents)
        y_axis_labels = [(100, 10000), (500, 0)]
        price_fn = calibrator.build_price_mapping(y_axis_labels)

        assert price_fn(100) == 10000
        assert price_fn(500) == 0

    def test_interpolates_between_points(self, calibrator: Calibrator) -> None:
        """Mapping should linearly interpolate between calibration points."""
        # pixel_y=100 -> 10000 cents, pixel_y=500 -> 0 cents
        # Midpoint pixel_y=300 -> 5000 cents
        y_axis_labels = [(100, 10000), (500, 0)]
        price_fn = calibrator.build_price_mapping(y_axis_labels)

        result = price_fn(300)
        assert result == 5000, (
            f"Expected 5000 cents at midpoint pixel 300, got {result}"
        )

    def test_handles_reversed_axis(self, calibrator: Calibrator) -> None:
        """Charts typically have y=0 at top, prices increasing downward-to-upward.

        In a standard chart: lower pixel_y = higher price (top of chart).
        This test verifies the mapping handles that correctly.
        """
        # Top of chart (pixel_y=80) = $100, bottom (pixel_y=700) = $0
        y_axis_labels = [(80, 10000), (700, 0)]
        price_fn = calibrator.build_price_mapping(y_axis_labels)

        # Higher on chart (lower pixel_y) should give higher price
        assert price_fn(80) > price_fn(700)
        assert price_fn(80) == 10000
        assert price_fn(700) == 0

    def test_interpolates_with_multiple_points(
        self, calibrator: Calibrator
    ) -> None:
        """Mapping should work with 3+ calibration points."""
        y_axis_labels = [(100, 10000), (300, 5000), (500, 0)]
        price_fn = calibrator.build_price_mapping(y_axis_labels)

        assert price_fn(100) == 10000
        assert price_fn(300) == 5000
        assert price_fn(500) == 0

        # Interpolate between first and second point: pixel 200 -> 7500
        assert price_fn(200) == 7500

    def test_single_point_returns_that_value(
        self, calibrator: Calibrator
    ) -> None:
        """With only one calibration point, any pixel should map to that price."""
        y_axis_labels = [(300, 5000)]
        price_fn = calibrator.build_price_mapping(y_axis_labels)

        assert price_fn(0) == 5000
        assert price_fn(300) == 5000
        assert price_fn(999) == 5000


class TestBuildDateMapping:
    """Tests for Calibrator.build_date_mapping (pixel_x -> date)."""

    def test_maps_known_date_points_exactly(
        self, calibrator: Calibrator
    ) -> None:
        """Mapping should return exact dates for known calibration points."""
        x_axis_labels = [
            (100, date(2024, 1, 1)),
            (1900, date(2025, 1, 1)),
        ]
        date_fn = calibrator.build_date_mapping(x_axis_labels)

        assert date_fn(100) == date(2024, 1, 1)
        assert date_fn(1900) == date(2025, 1, 1)

    def test_interpolates_dates_between_points(
        self, calibrator: Calibrator
    ) -> None:
        """Mapping should interpolate dates proportionally between points."""
        x_axis_labels = [
            (100, date(2024, 1, 1)),
            (1900, date(2025, 1, 1)),
        ]
        date_fn = calibrator.build_date_mapping(x_axis_labels)

        # Midpoint pixel 1000 -> roughly mid-year 2024
        mid_date = date_fn(1000)
        assert isinstance(mid_date, date)
        # Should be approximately mid-2024 (June/July)
        assert mid_date.year == 2024
        assert 5 <= mid_date.month <= 8, (
            f"Expected month 5-8 for midpoint, got {mid_date.month}"
        )

    def test_dates_increase_with_pixel_x(
        self, calibrator: Calibrator
    ) -> None:
        """Higher pixel_x should map to later dates (left-to-right chronological)."""
        x_axis_labels = [
            (100, date(2024, 1, 1)),
            (1900, date(2025, 1, 1)),
        ]
        date_fn = calibrator.build_date_mapping(x_axis_labels)

        date_left = date_fn(400)
        date_mid = date_fn(1000)
        date_right = date_fn(1600)

        assert date_left < date_mid < date_right, (
            f"Dates should increase: {date_left} < {date_mid} < {date_right}"
        )

    def test_interpolates_with_multiple_date_points(
        self, calibrator: Calibrator
    ) -> None:
        """Mapping should handle 3+ calibration date points."""
        x_axis_labels = [
            (100, date(2024, 1, 1)),
            (1000, date(2024, 7, 1)),
            (1900, date(2025, 1, 1)),
        ]
        date_fn = calibrator.build_date_mapping(x_axis_labels)

        assert date_fn(100) == date(2024, 1, 1)
        assert date_fn(1000) == date(2024, 7, 1)
        assert date_fn(1900) == date(2025, 1, 1)

    def test_single_date_point_returns_that_date(
        self, calibrator: Calibrator
    ) -> None:
        """With only one calibration point, any pixel should map to that date."""
        x_axis_labels = [(1000, date(2024, 6, 15))]
        date_fn = calibrator.build_date_mapping(x_axis_labels)

        assert date_fn(0) == date(2024, 6, 15)
        assert date_fn(1000) == date(2024, 6, 15)
        assert date_fn(1900) == date(2024, 6, 15)
