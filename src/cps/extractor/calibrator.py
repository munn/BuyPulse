"""Calibrator — pixel-to-value mapping for CCC chart axes.

Builds linear interpolation functions that convert pixel coordinates
to price (cents) or date values based on axis calibration points.
"""

from collections.abc import Callable
from datetime import date


class Calibrator:
    """Builds mapping functions from pixel coordinates to chart values."""

    def __init__(self) -> None:
        """Initialize Calibrator (stateless — all config via method args)."""

    def build_price_mapping(
        self, y_axis_labels: list[tuple[int, int]]
    ) -> Callable[[int], int]:
        """Build a pixel_y -> price_cents interpolation function.

        Args:
            y_axis_labels: List of (pixel_y, price_cents) calibration points.

        Returns:
            A function that maps any pixel_y to an interpolated price in cents.
        """
        if len(y_axis_labels) == 1:
            constant_price = y_axis_labels[0][1]
            return lambda _pixel_y, _p=constant_price: _p

        # Sort by pixel_y (ascending)
        sorted_points = sorted(y_axis_labels, key=lambda p: p[0])
        pixels = [p[0] for p in sorted_points]
        prices = [p[1] for p in sorted_points]

        def price_fn(pixel_y: int) -> int:
            # Clamp to range
            if pixel_y <= pixels[0]:
                return prices[0]
            if pixel_y >= pixels[-1]:
                return prices[-1]

            # Find the two surrounding calibration points
            for i in range(len(pixels) - 1):
                if pixels[i] <= pixel_y <= pixels[i + 1]:
                    # Linear interpolation
                    span = pixels[i + 1] - pixels[i]
                    fraction = (pixel_y - pixels[i]) / span
                    interpolated = prices[i] + fraction * (prices[i + 1] - prices[i])
                    return round(interpolated)

            return prices[-1]  # Fallback (should not be reached)

        return price_fn

    def build_date_mapping(
        self, x_axis_labels: list[tuple[int, date]]
    ) -> Callable[[int], date]:
        """Build a pixel_x -> date interpolation function.

        Args:
            x_axis_labels: List of (pixel_x, date) calibration points.

        Returns:
            A function that maps any pixel_x to an interpolated date.
        """
        if len(x_axis_labels) == 1:
            constant_date = x_axis_labels[0][1]
            return lambda _pixel_x, _d=constant_date: _d

        # Sort by pixel_x (ascending)
        sorted_points = sorted(x_axis_labels, key=lambda p: p[0])
        pixels = [p[0] for p in sorted_points]
        ordinals = [p[1].toordinal() for p in sorted_points]

        def date_fn(pixel_x: int) -> date:
            # Clamp to range
            if pixel_x <= pixels[0]:
                return date.fromordinal(ordinals[0])
            if pixel_x >= pixels[-1]:
                return date.fromordinal(ordinals[-1])

            # Find the two surrounding calibration points
            for i in range(len(pixels) - 1):
                if pixels[i] <= pixel_x <= pixels[i + 1]:
                    span = pixels[i + 1] - pixels[i]
                    fraction = (pixel_x - pixels[i]) / span
                    interpolated_ordinal = ordinals[i] + fraction * (
                        ordinals[i + 1] - ordinals[i]
                    )
                    return date.fromordinal(round(interpolated_ordinal))

            return date.fromordinal(ordinals[-1])  # Fallback

        return date_fn
