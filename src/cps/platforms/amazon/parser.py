"""Amazon platform parser — extracts prices from CCC chart images.

Wraps the existing PixelAnalyzer, OcrReader, and Validator to produce
standardized PriceRecords and PriceSummaryData.
"""

from pathlib import Path

from cps.extractor.ocr_reader import OcrReader
from cps.extractor.pixel_analyzer import PixelAnalyzer
from cps.pipeline.validator import Validator
from cps.platforms.protocol import (
    FetchResult,
    ParseResult,
    PriceRecord,
    PriceSummaryData,
)


class AmazonParser:
    """Parses CCC chart PNG images into price records."""

    def __init__(self) -> None:
        self._pixel_analyzer = PixelAnalyzer()
        self._ocr_reader = OcrReader()
        self._validator = Validator()

    def parse(self, fetch_result: FetchResult) -> ParseResult:
        """Extract price data from a CCC chart image."""
        if fetch_result.storage_path is None:
            return ParseResult(records=[], validation_status="failed")

        chart_path = Path(fetch_result.storage_path)

        pixel_data = self._pixel_analyzer.analyze(chart_path)
        ocr_result = self._ocr_reader.read(chart_path)

        # Build OCR comparison data for cross-validation
        ocr_compare: dict[str, dict[str, int]] = {}
        for price_type, legend_vals in ocr_result.legend.items():
            ocr_compare[price_type] = {}
            for key, val in legend_vals.items():
                if val and val.startswith("$"):
                    try:
                        cents = int(float(val.replace("$", "").replace(",", "")) * 100)
                        ocr_compare[price_type][key] = cents
                    except (ValueError, TypeError):
                        pass

        # Build pixel summary for validation
        pixel_summary: dict[str, dict[str, int]] = {}
        for price_type, points in pixel_data.items():
            if points:
                prices = [p for _, p in points]
                pixel_summary[price_type] = {
                    "lowest": min(prices),
                    "highest": max(prices),
                    "current": prices[-1],
                }

        validation = self._validator.validate(pixel_summary, ocr_compare)

        # Build PriceRecords from pixel data
        records: list[PriceRecord] = []
        for price_type, points in pixel_data.items():
            for recorded_date, price_cents in points:
                records.append(
                    PriceRecord(
                        price_type=price_type,
                        recorded_date=recorded_date,
                        price_cents=price_cents,
                        source="ccc_chart",
                    )
                )

        # Build PriceSummaryData — use dates corresponding to actual min/max prices
        summaries: list[PriceSummaryData] = []
        for price_type, summary in pixel_summary.items():
            pts = pixel_data.get(price_type, [])
            if pts:
                min_pair = min(pts, key=lambda p: p[1])  # (date, price) with lowest price
                max_pair = max(pts, key=lambda p: p[1])  # (date, price) with highest price
                last_pair = pts[-1]
            else:
                min_pair = max_pair = last_pair = (None, None)
            summaries.append(
                PriceSummaryData(
                    price_type=price_type,
                    lowest_price=summary.get("lowest"),
                    lowest_date=min_pair[0],
                    highest_price=summary.get("highest"),
                    highest_date=max_pair[0],
                    current_price=summary.get("current"),
                    current_date=last_pair[0],
                )
            )

        total_points = sum(len(pts) for pts in pixel_data.values())

        return ParseResult(
            records=records,
            summaries=summaries,
            points_extracted=total_points,
            confidence=ocr_result.confidence,
            validation_passed=validation.passed,
            validation_status=validation.status,
        )
