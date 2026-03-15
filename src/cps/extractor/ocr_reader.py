"""OcrReader — extract text labels from CCC chart images.

Uses Pillow for image cropping and pytesseract for OCR to extract:
- Y-axis price labels (e.g., "$20.00")
- X-axis date labels (e.g., "Jan 2024")
- Legend text (lowest/highest/current prices)
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
    """

    y_axis_labels: list[tuple[int, str]] = field(default_factory=list)
    x_axis_labels: list[tuple[int, str]] = field(default_factory=list)
    legend: dict[str, dict[str, str | None]] = field(default_factory=dict)
    confidence: float = 0.0


# Chart layout constants (CCC chart dimensions)
_CHART_LEFT = 100
_CHART_RIGHT = 1900
_CHART_TOP = 80
_CHART_BOTTOM = 700

# Y-axis region
_YAXIS_X_START = 0
_YAXIS_X_END = 70

# X-axis region
_XAXIS_Y_START = 705
_XAXIS_Y_END = 725

# Legend region
_LEGEND_X_START = 1595
_LEGEND_X_END = 1735
_LEGEND_Y_START = 80
_LEGEND_Y_END = 130

# Known legend color box positions (y-center of each colored square)
_LEGEND_COLOR_BOXES = {
    "amazon": {"color": (34, 139, 34), "y_range": (20, 32)},
    "new": {"color": (0, 0, 255), "y_range": (40, 52)},
    "used": {"color": (255, 0, 0), "y_range": (60, 72)},
}

# Price pattern: $XX.XX or $X,XXX.XX
_PRICE_PATTERN = re.compile(r"\$[\d,]+\.?\d*")

# Date pattern: Mon YYYY
_DATE_PATTERN = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*\d{4}"
)


def _try_import_pytesseract():
    """Attempt to import pytesseract; return module or None."""
    try:
        import pytesseract

        # Verify tesseract binary is available
        pytesseract.get_tesseract_version()
        return pytesseract
    except Exception:
        return None


class OcrReader:
    """Extract text from CCC chart images using OCR."""

    def __init__(self) -> None:
        """Initialize OcrReader."""
        self._pytesseract = _try_import_pytesseract()

    def read(self, image_path: Path) -> OcrResult:
        """Read and extract text from a CCC chart image.

        Args:
            image_path: Path to the chart PNG file.

        Returns:
            OcrResult with extracted labels, legend, and confidence score.
        """
        if self._pytesseract is None:
            return OcrResult(confidence=0.0)

        try:
            img = Image.open(image_path).convert("RGB")
        except Exception:
            return OcrResult(confidence=0.0)

        y_axis_labels = self._extract_y_axis_labels(img)
        x_axis_labels = self._extract_x_axis_labels(img)
        has_curves = self._detect_data_curves(img)
        legend = self._extract_legend(img)
        confidence = self._compute_confidence(
            y_axis_labels, x_axis_labels, legend, has_curves
        )

        return OcrResult(
            y_axis_labels=y_axis_labels,
            x_axis_labels=x_axis_labels,
            legend=legend,
            confidence=confidence,
        )

    def _extract_y_axis_labels(
        self, img: Image.Image
    ) -> list[tuple[int, str]]:
        """Extract Y-axis price labels by finding text clusters and OCR-ing them."""
        labels: list[tuple[int, str]] = []

        # Find vertical positions of text clusters in the Y-axis area
        text_clusters = self._find_y_axis_text_clusters(img)

        for center_y in text_clusters:
            crop = img.crop((
                _YAXIS_X_START,
                center_y - 10,
                _YAXIS_X_END,
                center_y + 10,
            ))
            # Scale up for better OCR accuracy
            crop = crop.resize((280, 80))

            try:
                text = self._pytesseract.image_to_string(
                    crop, config="--psm 7"
                ).strip()
            except Exception:
                continue

            # Check if it looks like a price
            if _PRICE_PATTERN.search(text):
                match = _PRICE_PATTERN.search(text)
                labels.append((center_y, match.group()))

        return labels

    def _find_y_axis_text_clusters(self, img: Image.Image) -> list[int]:
        """Find y-positions of text clusters in the Y-axis area.

        Scans for rows with multiple dark pixels in the left margin,
        then groups them into clusters and returns cluster centers.
        """
        dark_rows: list[int] = []

        for y in range(_CHART_TOP - 20, _CHART_BOTTOM + 20):
            dark_count = 0
            for x in range(_YAXIS_X_START, _YAXIS_X_END):
                r, g, b = img.getpixel((x, y))
                if r < 100 and g < 100 and b < 100:
                    dark_count += 1
            if dark_count >= 3:
                dark_rows.append(y)

        # Group consecutive rows into clusters
        clusters: list[list[int]] = []
        current_cluster: list[int] = []

        for row in dark_rows:
            if current_cluster and row - current_cluster[-1] > 3:
                clusters.append(current_cluster)
                current_cluster = [row]
            else:
                current_cluster.append(row)

        if current_cluster:
            clusters.append(current_cluster)

        # Return center of each cluster
        return [
            (cluster[0] + cluster[-1]) // 2
            for cluster in clusters
            if len(cluster) >= 2
        ]

    def _extract_x_axis_labels(
        self, img: Image.Image
    ) -> list[tuple[int, str]]:
        """Extract X-axis date labels by finding text clusters and OCR-ing them."""
        labels: list[tuple[int, str]] = []

        # Find horizontal positions of text clusters in the X-axis area
        text_clusters = self._find_x_axis_text_clusters(img)

        for center_x in text_clusters:
            crop = img.crop((
                center_x - 50,
                _XAXIS_Y_START,
                center_x + 50,
                _XAXIS_Y_END,
            ))
            # Scale up for better OCR accuracy
            crop = crop.resize((400, 80))

            try:
                text = self._pytesseract.image_to_string(
                    crop, config="--psm 7"
                ).strip()
            except Exception:
                continue

            # Check if it looks like a date (Mon YYYY)
            match = _DATE_PATTERN.search(text)
            if match:
                labels.append((center_x, match.group()))

        return labels

    def _find_x_axis_text_clusters(self, img: Image.Image) -> list[int]:
        """Find x-positions of text clusters in the X-axis area.

        Scans for columns with dark pixels in the bottom margin,
        then groups them into clusters and returns cluster centers.
        """
        dark_cols: list[int] = []

        for x in range(_CHART_LEFT - 20, _CHART_RIGHT + 50):
            dark_count = 0
            for y in range(_XAXIS_Y_START, _XAXIS_Y_END):
                r, g, b = img.getpixel((x, y))
                if r < 150 and g < 150 and b < 150:
                    dark_count += 1
            if dark_count >= 2:
                dark_cols.append(x)

        # Group consecutive columns into clusters
        clusters: list[list[int]] = []
        current_cluster: list[int] = []

        for col in dark_cols:
            if current_cluster and col - current_cluster[-1] > 5:
                clusters.append(current_cluster)
                current_cluster = [col]
            else:
                current_cluster.append(col)

        if current_cluster:
            clusters.append(current_cluster)

        # Return center of each cluster (only substantial clusters)
        return [
            (cluster[0] + cluster[-1]) // 2
            for cluster in clusters
            if len(cluster) >= 5
        ]

    def _extract_legend(
        self, img: Image.Image
    ) -> dict[str, dict[str, str | None]]:
        """Extract legend text (Lowest/Highest/Current) from the chart.

        First detects which price types have colored legend boxes,
        then OCRs the legend text area below those boxes.
        """
        legend: dict[str, dict[str, str | None]] = {}

        # Detect which price types have legend color boxes
        detected_types = self._detect_legend_color_boxes(img)

        if not detected_types:
            return legend

        # OCR the full legend text block
        crop = img.crop((
            _LEGEND_X_START,
            _LEGEND_Y_START,
            _LEGEND_X_END,
            _LEGEND_Y_END,
        ))
        crop = crop.resize((560, 200))

        try:
            text = self._pytesseract.image_to_string(
                crop, config="--psm 6"
            ).strip()
        except Exception:
            return legend

        if not text:
            return legend

        # Parse legend text for Lowest/Highest/Current
        legend_data = self._parse_legend_text(text)

        if legend_data:
            # Assign legend data to the first detected price type
            # (CCC charts typically show combined legend info)
            for price_type in detected_types:
                legend[price_type] = legend_data
                break

        return legend

    def _detect_legend_color_boxes(self, img: Image.Image) -> list[str]:
        """Detect which price types have colored legend boxes.

        Returns list of detected price type keys (e.g., ["amazon", "new", "used"]).
        """
        detected: list[str] = []
        search_x_start = 1550
        search_x_end = 1650

        for price_type, info in _LEGEND_COLOR_BOXES.items():
            target_r, target_g, target_b = info["color"]
            y_start, y_end = info["y_range"]
            found = False

            for y in range(y_start, y_end + 1):
                for x in range(search_x_start, search_x_end):
                    try:
                        r, g, b = img.getpixel((x, y))
                    except IndexError:
                        continue
                    if r == target_r and g == target_g and b == target_b:
                        found = True
                        break
                if found:
                    break

            if found:
                detected.append(price_type)

        return detected

    def _parse_legend_text(
        self, text: str
    ) -> dict[str, str | None]:
        """Parse legend text lines for Lowest/Highest/Current values.

        Expected patterns:
            Lowest $15.00 (Aug 2024)
            Highest $70.00 (Mar 2024)
            Current $50.00
        """
        result: dict[str, str | None] = {
            "lowest": None,
            "lowest_date": None,
            "highest": None,
            "highest_date": None,
            "current": None,
        }

        lines = text.split("\n")
        for line in lines:
            line_lower = line.strip().lower()

            if "lowest" in line_lower:
                price_match = _PRICE_PATTERN.search(line)
                if price_match:
                    result["lowest"] = price_match.group()
                date_match = re.search(r"\(([^)]+)\)", line)
                if date_match:
                    result["lowest_date"] = date_match.group(1)

            elif "highest" in line_lower:
                price_match = _PRICE_PATTERN.search(line)
                if price_match:
                    result["highest"] = price_match.group()
                date_match = re.search(r"\(([^)]+)\)", line)
                if date_match:
                    result["highest_date"] = date_match.group(1)

            elif "current" in line_lower:
                price_match = _PRICE_PATTERN.search(line)
                if price_match:
                    result["current"] = price_match.group()

        return result

    def _detect_data_curves(self, img: Image.Image) -> bool:
        """Check whether the chart contains any visible data curves.

        Samples the chart area for known curve colors (green, blue, red).
        """
        curve_colors = [
            (34, 139, 34),   # Amazon green
            (0, 0, 255),     # 3rd party new blue
            (255, 0, 0),     # Used red
        ]

        for x in range(_CHART_LEFT, _CHART_RIGHT + 1, 50):
            for y in range(_CHART_TOP, _CHART_BOTTOM + 1, 10):
                try:
                    pixel = img.getpixel((x, y))
                except IndexError:
                    continue
                for target in curve_colors:
                    if pixel == target:
                        return True

        return False

    def _compute_confidence(
        self,
        y_axis_labels: list[tuple[int, str]],
        x_axis_labels: list[tuple[int, str]],
        legend: dict[str, dict[str, str | None]],
        has_curves: bool,
    ) -> float:
        """Compute a confidence score based on extraction success.

        A chart with no visible data curves (no-data chart) gets a heavy
        penalty since the chart frame alone is not meaningful data.

        Scoring:
        - Has data curves: 0.4 (required for high confidence)
        - Y-axis labels: up to 0.15
        - X-axis labels: up to 0.15
        - Legend: up to 0.3 (at least 1 entry with fields)
        """
        score = 0.0

        # Curve presence is the primary confidence signal
        if has_curves:
            score += 0.4

        # Y-axis: 0.15 max
        expected_y = 6
        y_score = min(len(y_axis_labels) / expected_y, 1.0) * 0.15
        score += y_score

        # X-axis: 0.15 max
        expected_x = 5
        x_score = min(len(x_axis_labels) / expected_x, 1.0) * 0.15
        score += x_score

        # Legend: 0.3 max
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
