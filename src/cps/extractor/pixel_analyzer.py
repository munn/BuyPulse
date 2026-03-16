"""PixelAnalyzer — extract price curves from CCC chart images.

Scans chart pixels for known curve colors and converts pixel positions
to (date, price_cents) data points.

Curve colors and layout verified from real CCC charts (spike 2026-03-15).
"""

import math
from datetime import date
from pathlib import Path

from PIL import Image


# Proportional chart layout (fraction of image width/height)
_CHART_X_FRAC = (0.04, 0.98)
_CHART_Y_FRAC = (0.04, 0.76)
_YAXIS_X_FRAC = (0.0, 0.055)
_XAXIS_Y_FRAC = (0.76, 0.82)

# Real CCC curve colors (verified from spike data)
_CURVE_COLORS: dict[str, tuple[int, int, int]] = {
    "amazon": (99, 168, 94),
    "new": (0, 51, 204),
    "used": (204, 51, 0),
}

# Color matching tolerance (Euclidean distance in RGB space)
_COLOR_TOLERANCE = 30

# Column sampling step (every Nth pixel to reduce data volume)
_COLUMN_STEP = 4


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
        pass

    def analyze(
        self, image_path: Path
    ) -> dict[str, list[tuple[date, int]]]:
        """Analyze a CCC chart image and extract curve data.

        Returns:
            Dict mapping price_type ("amazon", "new", "used") to sorted
            list of (date, price_cents) tuples.
        """
        try:
            img = Image.open(image_path).convert("RGB")
        except Exception:
            return {}

        w, h = img.size

        # Compute pixel boundaries from proportions
        chart_left = int(w * _CHART_X_FRAC[0])
        chart_right = int(w * _CHART_X_FRAC[1])
        chart_top = int(h * _CHART_Y_FRAC[0])
        chart_bottom = int(h * _CHART_Y_FRAC[1])

        # Detect Y-axis range
        price_top_cents, price_bottom_cents = self._detect_y_axis_range(
            img, w, h
        )

        # Detect X-axis date range
        date_start, date_end = self._detect_x_axis_range(img, w, h)

        # Scan columns for curve colors
        raw_curves: dict[str, list[tuple[int, int]]] = {
            name: [] for name in _CURVE_COLORS
        }

        for x in range(chart_left, chart_right + 1, _COLUMN_STEP):
            column_hits = self._scan_column(img, x, chart_top, chart_bottom)
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
                    pixel_x, date_start, date_end,
                    chart_left, chart_right
                )
                price_cents = self._pixel_y_to_price(
                    pixel_y, price_top_cents, price_bottom_cents,
                    chart_top, chart_bottom
                )
                price_cents = max(
                    0, min(price_cents, max(price_top_cents, price_bottom_cents))
                )
                data_points.append((point_date, price_cents))

            data_points.sort(key=lambda p: p[0])
            result[color_name] = data_points

        return result

    def _scan_column(
        self, img: Image.Image, x: int,
        chart_top: int, chart_bottom: int
    ) -> dict[str, int]:
        """Scan a single column for curve color matches.

        For each target color, finds the topmost matching pixel.
        """
        hits: dict[str, int] = {}

        for y in range(chart_top, chart_bottom + 1):
            try:
                pixel_rgb = img.getpixel((x, y))
            except IndexError:
                continue

            for color_name, target_rgb in _CURVE_COLORS.items():
                if color_name in hits:
                    continue

                if _color_distance(pixel_rgb, target_rgb) <= _COLOR_TOLERANCE:
                    hits[color_name] = y

            if len(hits) == len(_CURVE_COLORS):
                break

        return hits

    def _detect_y_axis_range(
        self, img: Image.Image, w: int, h: int
    ) -> tuple[int, int]:
        """Detect the Y-axis price range using full-strip OCR.

        Returns:
            (price_at_top_cents, price_at_bottom_cents)
        """
        try:
            import pytesseract
        except ImportError:
            return (10000, 0)

        x_end = int(w * _YAXIS_X_FRAC[1])
        y_start = int(h * _CHART_Y_FRAC[0])
        y_end = int(h * _CHART_Y_FRAC[1])

        # Full strip OCR with threshold preprocessing
        strip = img.crop((0, y_start, x_end, y_end))
        gray = strip.convert("L")
        big = gray.resize((gray.width * 5, gray.height * 5), Image.LANCZOS)
        threshold = big.point(lambda p: 255 if p > 128 else 0)

        try:
            text = pytesseract.image_to_string(
                threshold,
                config="--psm 6 -c tessedit_char_whitelist=$0123456789,."
            ).strip()
        except Exception:
            return (10000, 0)

        # Parse prices (require $ sign to avoid OCR noise like bare "9750")
        import re
        prices_cents = []
        for match in re.finditer(r"\$([\d,]+)\.?(\d{0,2})", text):
            dollars_str = match.group(1).replace(",", "")
            cents_str = match.group(2) if match.group(2) else "00"
            cents_str = cents_str.ljust(2, "0")
            try:
                cents = int(dollars_str) * 100 + int(cents_str)
                if cents > 0:
                    prices_cents.append(cents)
            except ValueError:
                continue

        if len(prices_cents) >= 2:
            # Y-axis prices are descending (top=highest, bottom=lowest)
            # First recognized price = top label, last = bottom label
            return (prices_cents[0], prices_cents[-1])
        elif len(prices_cents) == 1:
            return (prices_cents[0], 0)

        return (10000, 0)

    def _parse_price_to_cents(self, text: str) -> int | None:
        """Parse a price string like '$100.00' or '$1,000' to cents."""
        import re

        match = re.search(r"\$?([\d,]+)\.?(\d{0,2})", text)
        if not match:
            return None

        dollars_str = match.group(1).replace(",", "")
        cents_str = match.group(2) if match.group(2) else "00"
        cents_str = cents_str.ljust(2, "0")

        try:
            return int(dollars_str) * 100 + int(cents_str)
        except ValueError:
            return None

    def _detect_x_axis_range(
        self, img: Image.Image, w: int, h: int
    ) -> tuple[date, date]:
        """Detect the X-axis date range from chart content."""
        try:
            import pytesseract
        except ImportError:
            return (date(2024, 1, 1), date(2026, 3, 1))

        chart_left = int(w * _CHART_X_FRAC[0])
        chart_right = int(w * _CHART_X_FRAC[1])
        y_start = int(h * _XAXIS_Y_FRAC[0])
        y_end = int(h * _XAXIS_Y_FRAC[1])

        # OCR leftmost label
        left_crop = img.crop((
            max(0, chart_left - 40), y_start,
            chart_left + 60, y_end
        ))
        left_crop = left_crop.resize((left_crop.width * 4, left_crop.height * 4))

        # OCR rightmost label
        right_crop = img.crop((
            max(0, chart_right - 60), y_start,
            min(w, chart_right + 40), y_end
        ))
        right_crop = right_crop.resize((right_crop.width * 4, right_crop.height * 4))

        start_date = date(2024, 1, 1)
        end_date = date(2026, 3, 1)

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
        """Parse 'Mon YYYY' or 'Mon' + 'YY' to a date."""
        import re

        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4,
            "may": 5, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }

        # Try full year first: "Mar 2026"
        match = re.search(
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d{4})",
            text,
        )
        if match:
            month = months.get(match.group(1).lower())
            year = int(match.group(2))
            if month:
                return date(year, month, 1)

        # Try short year: "Mar '26" or "'26"
        match = re.search(r"'(\d{2})", text)
        if match:
            year = 2000 + int(match.group(1))
            # Try to find month before it
            month_match = re.search(
                r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", text
            )
            month = 1
            if month_match:
                month = months.get(month_match.group(1).lower(), 1)
            return date(year, month, 1)

        return None

    def _pixel_x_to_date(
        self, pixel_x: int, start_date: date, end_date: date,
        chart_left: int, chart_right: int
    ) -> date:
        """Convert a pixel x-coordinate to a date."""
        x_range = chart_right - chart_left
        if x_range == 0:
            return start_date

        fraction = (pixel_x - chart_left) / x_range
        fraction = max(0.0, min(1.0, fraction))

        start_ord = start_date.toordinal()
        end_ord = end_date.toordinal()
        result_ord = round(start_ord + fraction * (end_ord - start_ord))

        return date.fromordinal(result_ord)

    def _pixel_y_to_price(
        self, pixel_y: int, price_top_cents: int, price_bottom_cents: int,
        chart_top: int, chart_bottom: int
    ) -> int:
        """Convert a pixel y-coordinate to price in cents."""
        y_range = chart_bottom - chart_top
        if y_range == 0:
            return price_top_cents

        fraction = (pixel_y - chart_top) / y_range
        fraction = max(0.0, min(1.0, fraction))

        price = price_top_cents + fraction * (
            price_bottom_cents - price_top_cents
        )
        return round(price)
