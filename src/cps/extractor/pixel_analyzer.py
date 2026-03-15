"""PixelAnalyzer — extract price curves from CCC chart images.

Scans chart pixels for known curve colors (Amazon green, 3rd-party blue,
Used red) and converts pixel positions to (date, price_cents) data points.
"""

import math
from datetime import date
from pathlib import Path

from PIL import Image


# Chart area boundaries (pixels)
_CHART_LEFT = 100
_CHART_RIGHT = 1900
_CHART_TOP = 80
_CHART_BOTTOM = 700

# Target curve colors and their RGB values
_CURVE_COLORS: dict[str, tuple[int, int, int]] = {
    "amazon": (34, 139, 34),
    "new": (0, 0, 255),
    "used": (255, 0, 0),
}

# Color matching tolerance (Euclidean distance in RGB space)
_COLOR_TOLERANCE = 50

# Column sampling step (every Nth pixel to reduce data volume)
_COLUMN_STEP = 10

# Y-axis label approximate positions (center-y of text clusters)
# These are consistent across all chart types based on chart geometry
_Y_LABEL_POSITIONS = [77, 201, 325, 449, 573, 697]


def _color_distance(
    c1: tuple[int, int, int], c2: tuple[int, int, int]
) -> float:
    """Compute Euclidean distance between two RGB colors."""
    return math.sqrt(
        (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2
    )


class PixelAnalyzer:
    """Analyze CCC chart images to extract price curve data points."""

    def __init__(self) -> None:
        """Initialize PixelAnalyzer."""

    def analyze(
        self, image_path: Path
    ) -> dict[str, list[tuple[date, int]]]:
        """Analyze a CCC chart image and extract curve data.

        Args:
            image_path: Path to the chart PNG file.

        Returns:
            Dict mapping price_type ("amazon", "new", "used") to sorted
            list of (date, price_cents) tuples.
        """
        try:
            img = Image.open(image_path).convert("RGB")
        except Exception:
            return {}

        # Detect Y-axis range by reading the topmost and bottommost label values
        price_top_cents, price_bottom_cents = self._detect_y_axis_range(img)

        # Detect X-axis date range
        date_start, date_end = self._detect_x_axis_range(img)

        # Scan columns for curve colors
        raw_curves: dict[str, list[tuple[int, int]]] = {
            name: [] for name in _CURVE_COLORS
        }

        for x in range(_CHART_LEFT, _CHART_RIGHT + 1, _COLUMN_STEP):
            column_hits = self._scan_column(img, x)
            for color_name, pixel_y in column_hits.items():
                raw_curves[color_name].append((x, pixel_y))

        # Convert pixel coordinates to (date, price_cents)
        result: dict[str, list[tuple[date, int]]] = {}

        for color_name, pixel_points in raw_curves.items():
            if not pixel_points:
                continue

            data_points: list[tuple[date, int]] = []
            for pixel_x, pixel_y in pixel_points:
                point_date = self._pixel_x_to_date(
                    pixel_x, date_start, date_end
                )
                price_cents = self._pixel_y_to_price(
                    pixel_y, price_top_cents, price_bottom_cents
                )
                # Clamp price to valid range
                price_cents = max(
                    0, min(price_cents, max(price_top_cents, price_bottom_cents))
                )
                data_points.append((point_date, price_cents))

            # Sort by date
            data_points.sort(key=lambda p: p[0])
            result[color_name] = data_points

        return result

    def _scan_column(
        self, img: Image.Image, x: int
    ) -> dict[str, int]:
        """Scan a single column for curve color matches.

        For each target color, finds the topmost matching pixel
        (which represents the curve's y-position at this x).

        Returns:
            Dict mapping color_name to the matched pixel_y.
        """
        hits: dict[str, int] = {}

        for y in range(_CHART_TOP, _CHART_BOTTOM + 1):
            try:
                pixel_rgb = img.getpixel((x, y))
            except IndexError:
                continue

            for color_name, target_rgb in _CURVE_COLORS.items():
                if color_name in hits:
                    continue  # Already found this color in this column

                if _color_distance(pixel_rgb, target_rgb) <= _COLOR_TOLERANCE:
                    hits[color_name] = y

            if len(hits) == len(_CURVE_COLORS):
                break  # Found all colors

        return hits

    def _detect_y_axis_range(
        self, img: Image.Image
    ) -> tuple[int, int]:
        """Detect the Y-axis price range from chart content.

        Uses OCR on the topmost and bottommost Y-axis labels to determine
        the price range. Falls back to heuristic detection.

        Returns:
            (price_at_top_cents, price_at_bottom_cents)
            For standard charts: (10000, 0) meaning $100 at top, $0 at bottom
            For edge charts: (100000, 0) meaning $1000 at top, $0 at bottom
        """
        try:
            import pytesseract
        except ImportError:
            return (10000, 0)  # Default: $0-$100

        # OCR the topmost Y-axis label to detect range
        top_label_y = _Y_LABEL_POSITIONS[0]  # ~77
        crop = img.crop((0, top_label_y - 10, 70, top_label_y + 10))
        crop = crop.resize((280, 80))

        try:
            text = pytesseract.image_to_string(crop, config="--psm 7").strip()
        except Exception:
            return (10000, 0)

        top_price_cents = self._parse_price_to_cents(text)
        if top_price_cents is not None:
            return (top_price_cents, 0)

        return (10000, 0)  # Default fallback

    def _parse_price_to_cents(self, text: str) -> int | None:
        """Parse a price string like '$100.00' or '$1000.00' to cents."""
        import re

        match = re.search(r"\$([\d,]+)\.?(\d{0,2})", text)
        if not match:
            return None

        dollars_str = match.group(1).replace(",", "")
        cents_str = match.group(2) if match.group(2) else "00"
        # Pad cents to 2 digits
        cents_str = cents_str.ljust(2, "0")

        try:
            return int(dollars_str) * 100 + int(cents_str)
        except ValueError:
            return None

    def _detect_x_axis_range(
        self, img: Image.Image
    ) -> tuple[date, date]:
        """Detect the X-axis date range from chart content.

        OCRs the leftmost and rightmost X-axis labels.

        Returns:
            (start_date, end_date)
        """
        try:
            import pytesseract
        except ImportError:
            return (date(2024, 1, 1), date(2025, 1, 1))

        # OCR leftmost label
        left_crop = img.crop((
            _CHART_LEFT - 50, 705, _CHART_LEFT + 50, 725
        ))
        left_crop = left_crop.resize((400, 80))

        # OCR rightmost label
        right_crop = img.crop((
            _CHART_RIGHT - 50, 705, _CHART_RIGHT + 50, 725
        ))
        right_crop = right_crop.resize((400, 80))

        start_date = date(2024, 1, 1)  # Default
        end_date = date(2025, 1, 1)  # Default

        try:
            left_text = pytesseract.image_to_string(
                left_crop, config="--psm 7"
            ).strip()
            parsed = self._parse_month_year(left_text)
            if parsed:
                start_date = parsed
        except Exception:
            pass

        try:
            right_text = pytesseract.image_to_string(
                right_crop, config="--psm 7"
            ).strip()
            parsed = self._parse_month_year(right_text)
            if parsed:
                end_date = parsed
        except Exception:
            pass

        return (start_date, end_date)

    def _parse_month_year(self, text: str) -> date | None:
        """Parse a 'Mon YYYY' string to a date (1st of that month)."""
        import re

        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4,
            "may": 5, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }

        match = re.search(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d{4})",
            text,
        )
        if not match:
            return None

        month_str = match.group(1).lower()
        year = int(match.group(2))
        month = months.get(month_str)
        if month is None:
            return None

        return date(year, month, 1)

    def _pixel_x_to_date(
        self, pixel_x: int, start_date: date, end_date: date
    ) -> date:
        """Convert a pixel x-coordinate to a date via linear interpolation."""
        x_range = _CHART_RIGHT - _CHART_LEFT
        if x_range == 0:
            return start_date

        fraction = (pixel_x - _CHART_LEFT) / x_range
        fraction = max(0.0, min(1.0, fraction))

        start_ord = start_date.toordinal()
        end_ord = end_date.toordinal()
        result_ord = round(start_ord + fraction * (end_ord - start_ord))

        return date.fromordinal(result_ord)

    def _pixel_y_to_price(
        self, pixel_y: int, price_top_cents: int, price_bottom_cents: int
    ) -> int:
        """Convert a pixel y-coordinate to price in cents.

        In chart coordinates: top of chart = high price, bottom = low price.
        pixel_y increases downward, so lower pixel_y = higher price.
        """
        y_range = _CHART_BOTTOM - _CHART_TOP
        if y_range == 0:
            return price_top_cents

        # fraction: 0.0 at top (CHART_TOP) to 1.0 at bottom (CHART_BOTTOM)
        fraction = (pixel_y - _CHART_TOP) / y_range
        fraction = max(0.0, min(1.0, fraction))

        # top = high price, bottom = low price
        price = price_top_cents + fraction * (
            price_bottom_cents - price_top_cents
        )
        return round(price)
