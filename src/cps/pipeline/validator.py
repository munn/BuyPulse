"""Cross-validation of pixel-extracted prices vs OCR legend values."""

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of pixel vs OCR cross-validation."""

    passed: bool
    details: dict[str, dict[str, bool]]
    status: str  # "success", "low_confidence", "failed"


TOLERANCE = 0.05  # ±5%


class Validator:
    """Compare pixel-extracted prices against OCR legend values."""

    def validate(
        self,
        pixel_data: dict[str, dict[str, int]],
        ocr_data: dict[str, dict[str, int]],
    ) -> ValidationResult:
        """Validate pixel data against OCR data.

        Args:
            pixel_data: {price_type: {metric: price_cents}}
            ocr_data: same structure from OCR

        Returns:
            ValidationResult with per-metric pass/fail and overall status.
        """
        if not pixel_data:
            has_missing = bool(ocr_data)
            return ValidationResult(
                passed=not has_missing,
                details={},
                status="low_confidence" if ocr_data else "success",
            )

        details: dict[str, dict[str, bool]] = {}
        total_checks = 0
        passed_checks = 0
        missing_checks = 0

        for price_type, pixel_metrics in pixel_data.items():
            details[price_type] = {}
            ocr_metrics = ocr_data.get(price_type, {})

            for metric, pixel_value in pixel_metrics.items():
                if metric not in ocr_metrics:
                    missing_checks += 1
                    continue

                ocr_value = ocr_metrics[metric]
                total_checks += 1

                if ocr_value == 0:
                    check_passed = pixel_value == 0
                else:
                    deviation = abs(pixel_value - ocr_value) / abs(ocr_value)
                    check_passed = deviation <= TOLERANCE

                details[price_type][metric] = check_passed
                if check_passed:
                    passed_checks += 1

        # Determine overall status
        if missing_checks > 0 and total_checks == 0:
            return ValidationResult(
                passed=False,
                details=details,
                status="low_confidence",
            )

        if total_checks == 0:
            return ValidationResult(
                passed=True,
                details=details,
                status="success",
            )

        failed_checks = total_checks - passed_checks
        all_passed = failed_checks == 0

        if all_passed and missing_checks == 0:
            status = "success"
        elif failed_checks > total_checks / 2:
            status = "failed"
        else:
            status = "low_confidence"

        return ValidationResult(
            passed=all_passed,
            details=details,
            status=status,
        )
