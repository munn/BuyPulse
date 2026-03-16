"""OcrReader — extract text labels from CCC chart images.

Uses Pillow for image cropping and pytesseract for OCR to extract:
- Y-axis price labels (e.g., "$20.00")
- X-axis date labels (e.g., "Jan 2024")
- Legend text (lowest/highest/current prices per price type)

Coordinates are derived proportionally from image dimensions based on
real CCC chart layout analysis (spike 2026-03-15).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image


@dataclass
class OcrResult:
    """Structured OCR output from a CCC chart image.

    Attributes:
        y_axis_labels: List of (pixel_y, price_string) tuples.
        x_axis_labels: List of (pixel_x, date_string) tuples.
        legend: Dict mapping price_type to field values.
        confidence: Float 0.0-1.0 indicating extraction quality.
        is_nodata: True if chart is a "no data" placeholder image.
    """

    y_axis_labels: list[tuple[int, str]] = field(default_factory=list)
    x_axis_labels: list[tuple[int, str]] = field(default_factory=list)
    legend: dict[str, dict[str, str | None]] = field(default_factory=dict)
    confidence: float = 0.0
    is_nodata: bool = False


# Proportional chart layout (fraction of image width/height)
# Derived from real CCC charts at 1710x1026 resolution
_YAXIS_X_FRAC = (0.0, 0.055)       # Y-axis text: x=[0, ~5.5%]
_CHART_Y_FRAC = (0.04, 0.76)       # Chart area: y=[4%, 76%]
_XAXIS_Y_FRAC = (0.76, 0.82)       # X-axis text: y=[76%, 82%]
_LEGEND_Y_FRAC = (0.82, 0.98)      # Legend: y=[82%, 98%]
_CHART_X_FRAC = (0.04, 0.98)       # Chart area: x=[4%, 98%]

# Real CCC curve colors (verified from spike data)
_CURVE_COLORS = {
    "amazon": (99, 168, 94),
    "new": (0, 51, 204),
    "used": (204, 51, 0),
}

_COLOR_TOLERANCE = 15

# Price pattern: $XX.XX or $X,XXX.XX
_PRICE_PATTERN = re.compile(r"\$[\d,]+\.?\d*")

# Date patterns
_DATE_PATTERN_FULL = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}"
)
_DATE_PATTERN_SHORT = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*'?\d{2,4}"
)

# No-data detection threshold (bytes)
_NODATA_SIZE_THRESHOLD = 30000


def _try_import_pytesseract():
    """Attempt to import pytesseract; return module or None."""
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return pytesseract
    except Exception:
        return None


def _color_match(pixel, target, tolerance=_COLOR_TOLERANCE):
    """Check if pixel color is within tolerance of target."""
    return all(abs(pixel[i] - target[i]) <= tolerance for i in range(3))


class OcrReader:
    """Extract text from CCC chart images using OCR."""

    def __init__(self) -> None:
        self._pytesseract = _try_import_pytesseract()

    def read(self, image_path: Path) -> OcrResult:
        """Read and extract text from a CCC chart image."""
        if self._pytesseract is None:
            return OcrResult(confidence=0.0)

        # Check for no-data image (small file size)
        try:
            file_size = image_path.stat().st_size
        except OSError:
            return OcrResult(confidence=0.0)

        try:
            img = Image.open(image_path).convert("RGB")
        except Exception:
            return OcrResult(confidence=0.0)

        # Detect no-data images
        if file_size < _NODATA_SIZE_THRESHOLD:
            if self._is_nodata_image(img):
                return OcrResult(confidence=0.0, is_nodata=True)

        w, h = img.size

        y_axis_labels = self._extract_y_axis_labels(img, w, h)
        x_axis_labels = self._extract_x_axis_labels(img, w, h)
        has_curves = self._detect_data_curves(img, w, h)
        legend = self._extract_legend(img, w, h)
        confidence = self._compute_confidence(
            y_axis_labels, x_axis_labels, legend, has_curves
        )

        return OcrResult(
            y_axis_labels=y_axis_labels,
            x_axis_labels=x_axis_labels,
            legend=legend,
            confidence=confidence,
        )

    def _is_nodata_image(self, img: Image.Image) -> bool:
        """Detect 'We can't find data' placeholder images."""
        w, h = img.size
        # Sample center area — no-data images are mostly white with text
        white_count = 0
        total = 0
        for y in range(h // 4, 3 * h // 4, 5):
            for x in range(w // 4, 3 * w // 4, 5):
                r, g, b = img.getpixel((x, y))
                total += 1
                if r > 240 and g > 240 and b > 240:
                    white_count += 1
        return total > 0 and (white_count / total) > 0.90

    def _extract_y_axis_labels(
        self, img: Image.Image, w: int, h: int
    ) -> list[tuple[int, str]]:
        """Extract Y-axis price labels using full-strip OCR.

        OCR-ing the entire Y-axis strip at once gives much better results
        than per-label OCR (Tesseract uses multi-line context).
        """
        x_end = int(w * _YAXIS_X_FRAC[1])
        y_start = int(h * _CHART_Y_FRAC[0])
        y_end = int(h * _CHART_Y_FRAC[1])

        # Full strip OCR with grayscale threshold preprocessing
        strip = img.crop((0, y_start, x_end, y_end))
        gray = strip.convert("L")
        big = gray.resize((gray.width * 5, gray.height * 5), Image.LANCZOS)
        threshold = big.point(lambda p: 255 if p > 128 else 0)

        try:
            text = self._pytesseract.image_to_string(
                threshold,
                config="--psm 6 -c tessedit_char_whitelist=$0123456789,."
            ).strip()
        except Exception:
            return []

        # Parse all prices from the strip
        prices = list(_PRICE_PATTERN.finditer(text))
        if not prices:
            return []

        # Map prices to evenly-spaced pixel positions within the strip
        strip_height = y_end - y_start
        n = len(prices)
        labels: list[tuple[int, str]] = []
        for i, match in enumerate(prices):
            # Evenly space labels within the chart Y range
            frac = (i + 0.5) / n
            pixel_y = y_start + int(frac * strip_height)
            labels.append((pixel_y, match.group()))

        return labels

    def _extract_x_axis_labels(
        self, img: Image.Image, w: int, h: int
    ) -> list[tuple[int, str]]:
        """Extract X-axis date labels using full-strip OCR.

        CCC X-axis format: "May Jul Sep Nov '23 Mar May Jul Sep Nov '24 ..."
        Labels are evenly spaced month abbreviations with year markers.
        """
        x_start = int(w * _CHART_X_FRAC[0])
        x_end = int(w * _CHART_X_FRAC[1])
        y_start = int(h * _XAXIS_Y_FRAC[0])
        y_end = int(h * _XAXIS_Y_FRAC[1])

        strip = img.crop((x_start, y_start, x_end, y_end))
        gray = strip.convert("L")
        big = gray.resize((gray.width * 3, gray.height * 3), Image.LANCZOS)
        threshold = big.point(lambda p: 255 if p > 140 else 0)

        try:
            text = self._pytesseract.image_to_string(
                threshold, config="--psm 7"
            ).strip()
        except Exception:
            return []

        # Parse month tokens and year markers from the OCR text
        tokens = text.split()
        month_names = {
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        }

        labels: list[tuple[int, str]] = []
        strip_width = x_end - x_start
        n_tokens = len(tokens)

        for i, token in enumerate(tokens):
            # Position: evenly spaced across the strip
            frac = (i + 0.5) / n_tokens
            pixel_x = x_start + int(frac * strip_width)

            if token in month_names:
                labels.append((pixel_x, token))
            elif token.startswith("'") and len(token) == 3:
                # Year marker like "'23", "'24"
                labels.append((pixel_x, token))

        return labels

    def _extract_legend(
        self, img: Image.Image, w: int, h: int
    ) -> dict[str, dict[str, str | None]]:
        """Extract legend table using full-strip OCR.

        Real CCC legend format (table at bottom):
            Price type     Lowest              Highest             Current
            Amazon         $399.00 (Jul 9, 24) $599.99 (Mar 11)   $599.00 (Mar 16)
            3rd party new  $539.99 (Aug 22)    $608.82 (Jan 16)   $599.00 (Mar 16)
            3rd party used $367.08 (Jun 25)    $739.30 (Jan 24)   $693.49 (Mar 16)
        """
        legend: dict[str, dict[str, str | None]] = {}

        y_start = int(h * _LEGEND_Y_FRAC[0])
        y_end = int(h * _LEGEND_Y_FRAC[1])

        strip = img.crop((0, y_start, w, y_end))
        gray = strip.convert("L")
        big = gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS)
        threshold = big.point(lambda p: 255 if p > 140 else 0)

        try:
            text = self._pytesseract.image_to_string(
                threshold, config="--psm 6"
            ).strip()
        except Exception:
            return legend

        if not text:
            return legend

        # Parse each line of the legend table
        for line in text.split("\n"):
            line_lower = line.strip().lower()
            if not line_lower:
                continue

            # Detect price type from line content
            price_type = None
            if "amazon" in line_lower and "3rd" not in line_lower:
                price_type = "amazon"
            elif "3rd party new" in line_lower or "3rd party_new" in line_lower:
                price_type = "new"
            elif "3rd party used" in line_lower or "3rd party_used" in line_lower:
                price_type = "used"

            if price_type is None:
                continue

            legend[price_type] = self._parse_legend_row(line)

        return legend

    def _parse_legend_row(self, text: str) -> dict[str, str | None]:
        """Parse a single legend row for Lowest/Highest/Current prices."""
        result: dict[str, str | None] = {
            "lowest": None,
            "lowest_date": None,
            "highest": None,
            "highest_date": None,
            "current": None,
        }

        # Find all prices with optional dates in the row
        prices = list(_PRICE_PATTERN.finditer(text))
        dates = list(re.finditer(r"\(([^)]+)\)", text))

        # CCC legend row format: "Type | $low (date) | $high (date) | $current (date)"
        # Prices appear in order: lowest, highest, current
        if len(prices) >= 1:
            result["lowest"] = prices[0].group()
        if len(prices) >= 2:
            result["highest"] = prices[1].group()
        if len(prices) >= 3:
            result["current"] = prices[2].group()

        if len(dates) >= 1:
            result["lowest_date"] = dates[0].group(1)
        if len(dates) >= 2:
            result["highest_date"] = dates[1].group(1)

        return result

    def _detect_data_curves(self, img: Image.Image, w: int, h: int) -> bool:
        """Check whether the chart contains any visible data curves."""
        x_start = int(w * _CHART_X_FRAC[0])
        x_end = int(w * _CHART_X_FRAC[1])
        y_start = int(h * _CHART_Y_FRAC[0])
        y_end = int(h * _CHART_Y_FRAC[1])

        for x in range(x_start, x_end, 30):
            for y in range(y_start, y_end, 10):
                try:
                    px = img.getpixel((x, y))
                except IndexError:
                    continue
                for color in _CURVE_COLORS.values():
                    if _color_match(px, color):
                        return True

        return False

    def _compute_confidence(
        self,
        y_axis_labels: list[tuple[int, str]],
        x_axis_labels: list[tuple[int, str]],
        legend: dict[str, dict[str, str | None]],
        has_curves: bool,
    ) -> float:
        """Compute a confidence score based on extraction success."""
        score = 0.0

        if has_curves:
            score += 0.4

        expected_y = 5
        y_score = min(len(y_axis_labels) / expected_y, 1.0) * 0.15
        score += y_score

        expected_x = 4
        x_score = min(len(x_axis_labels) / expected_x, 1.0) * 0.15
        score += x_score

        if legend:
            has_values = any(
                any(v is not None for v in entry.values())
                for entry in legend.values()
            )
            if has_values:
                score += 0.3
            else:
                score += 0.1

        return min(score, 1.0)
