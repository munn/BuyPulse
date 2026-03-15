"""T016: Unit tests for cps.pipeline.validator — cross-validation of pixel vs OCR data.

These tests verify:
- Pixel values within ±5% of OCR values pass validation
- Pixel values with >5% deviation fail validation
- Missing OCR values result in low_confidence status
- Overall status computed correctly (success / low_confidence / failed)
- Empty input dicts handled gracefully
"""

import pytest

from cps.pipeline.validator import ValidationResult, Validator


class TestValidationResultDataclass:
    """ValidationResult holds structured validation output."""

    def test_has_passed_field(self):
        result = ValidationResult(passed=True, details={}, status="success")
        assert result.passed is True

    def test_has_details_field(self):
        details = {"amazon": {"current": True, "lowest": True}}
        result = ValidationResult(passed=True, details=details, status="success")
        assert result.details == details

    def test_has_status_field(self):
        result = ValidationResult(passed=False, details={}, status="failed")
        assert result.status == "failed"


class TestValidatorWithinTolerance:
    """Pixel values within ±5% of OCR values should pass."""

    def test_exact_match_passes(self):
        """Identical pixel and OCR values → pass."""
        validator = Validator()
        pixel_data = {"amazon": {"current": 2999, "lowest": 1500, "highest": 7000}}
        ocr_data = {"amazon": {"current": 2999, "lowest": 1500, "highest": 7000}}

        result = validator.validate(pixel_data, ocr_data)

        assert result.passed is True
        assert result.status == "success"
        assert result.details["amazon"]["current"] is True
        assert result.details["amazon"]["lowest"] is True
        assert result.details["amazon"]["highest"] is True

    def test_within_5_percent_passes(self):
        """Pixel=2999, OCR=3050 → within 5% → pass."""
        validator = Validator()
        pixel_data = {"amazon": {"current": 2999, "lowest": 1500, "highest": 7000}}
        ocr_data = {"amazon": {"current": 3050, "lowest": 1520, "highest": 6900}}

        result = validator.validate(pixel_data, ocr_data)

        assert result.passed is True
        assert result.status == "success"
        assert result.details["amazon"]["current"] is True

    def test_boundary_exactly_5_percent_passes(self):
        """Exactly 5% deviation → should still pass (inclusive boundary)."""
        validator = Validator()
        # 5% of 2000 = 100, so 2100 is exactly at boundary
        pixel_data = {"amazon": {"current": 2000}}
        ocr_data = {"amazon": {"current": 2100}}

        result = validator.validate(pixel_data, ocr_data)

        assert result.details["amazon"]["current"] is True


class TestValidatorBeyondTolerance:
    """Pixel values with >5% deviation from OCR should fail."""

    def test_large_deviation_fails(self):
        """Pixel=2999, OCR=1999 → >5% deviation → fail."""
        validator = Validator()
        pixel_data = {"amazon": {"current": 2999, "lowest": 1500, "highest": 7000}}
        ocr_data = {"amazon": {"current": 1999, "lowest": 1500, "highest": 7000}}

        result = validator.validate(pixel_data, ocr_data)

        assert result.details["amazon"]["current"] is False

    def test_all_metrics_beyond_tolerance_fails(self):
        """All metrics off by >5% → overall failure."""
        validator = Validator()
        pixel_data = {"amazon": {"current": 2999, "lowest": 1500, "highest": 7000}}
        ocr_data = {"amazon": {"current": 1000, "lowest": 500, "highest": 2000}}

        result = validator.validate(pixel_data, ocr_data)

        assert result.passed is False
        assert result.details["amazon"]["current"] is False
        assert result.details["amazon"]["lowest"] is False
        assert result.details["amazon"]["highest"] is False


class TestValidatorMissingOCR:
    """Missing OCR values should skip validation and flag low_confidence."""

    def test_missing_ocr_price_type_flags_low_confidence(self):
        """Pixel data has 'amazon' but OCR data is empty → low_confidence."""
        validator = Validator()
        pixel_data = {"amazon": {"current": 2999, "lowest": 1500, "highest": 7000}}
        ocr_data = {}

        result = validator.validate(pixel_data, ocr_data)

        assert result.status == "low_confidence"

    def test_missing_ocr_metric_flags_low_confidence(self):
        """OCR data has price type but missing a metric → low_confidence."""
        validator = Validator()
        pixel_data = {"amazon": {"current": 2999, "lowest": 1500, "highest": 7000}}
        ocr_data = {"amazon": {"current": 3000}}  # missing lowest and highest

        result = validator.validate(pixel_data, ocr_data)

        assert result.status == "low_confidence"

    def test_partial_ocr_still_validates_available_metrics(self):
        """Available OCR metrics should still be validated even if some are missing."""
        validator = Validator()
        pixel_data = {"amazon": {"current": 2999, "lowest": 1500, "highest": 7000}}
        ocr_data = {"amazon": {"current": 3000}}

        result = validator.validate(pixel_data, ocr_data)

        # The current metric that IS present should be validated
        assert result.details["amazon"]["current"] is True


class TestValidatorOverallStatus:
    """Overall status computation: success / low_confidence / failed."""

    def test_all_pass_returns_success(self):
        """All metrics within tolerance → 'success'."""
        validator = Validator()
        pixel_data = {
            "amazon": {"current": 2999, "lowest": 1500, "highest": 7000},
            "new": {"current": 3100, "lowest": 1600, "highest": 7200},
        }
        ocr_data = {
            "amazon": {"current": 3000, "lowest": 1500, "highest": 7000},
            "new": {"current": 3100, "lowest": 1600, "highest": 7200},
        }

        result = validator.validate(pixel_data, ocr_data)

        assert result.status == "success"
        assert result.passed is True

    def test_some_fail_returns_low_confidence(self):
        """Some metrics fail but not majority → 'low_confidence'."""
        validator = Validator()
        pixel_data = {
            "amazon": {"current": 2999, "lowest": 1500, "highest": 7000},
        }
        ocr_data = {
            "amazon": {"current": 1000, "lowest": 1500, "highest": 7000},
        }

        result = validator.validate(pixel_data, ocr_data)

        assert result.status == "low_confidence"
        assert result.passed is False

    def test_majority_fail_returns_failed(self):
        """Majority of metrics fail → 'failed'."""
        validator = Validator()
        pixel_data = {
            "amazon": {"current": 2999, "lowest": 1500, "highest": 7000},
        }
        ocr_data = {
            "amazon": {"current": 1000, "lowest": 500, "highest": 2000},
        }

        result = validator.validate(pixel_data, ocr_data)

        assert result.status == "failed"
        assert result.passed is False

    def test_multiple_price_types_majority_logic(self):
        """Status considers all price types combined, not per-type."""
        validator = Validator()
        pixel_data = {
            "amazon": {"current": 2999, "lowest": 1500, "highest": 7000},
            "new": {"current": 3100, "lowest": 1600, "highest": 7200},
            "used": {"current": 1000, "lowest": 500, "highest": 2000},
        }
        ocr_data = {
            "amazon": {"current": 3000, "lowest": 1500, "highest": 7000},
            "new": {"current": 3100, "lowest": 1600, "highest": 7200},
            "used": {"current": 5000, "lowest": 3000, "highest": 9000},
        }

        result = validator.validate(pixel_data, ocr_data)

        # 6/9 pass → majority pass → low_confidence (some fail)
        assert result.status == "low_confidence"


class TestValidatorEmptyInputs:
    """Empty input dicts should be handled gracefully."""

    def test_both_empty(self):
        """Empty pixel_data and ocr_data → no crash, returns valid result."""
        validator = Validator()

        result = validator.validate({}, {})

        assert isinstance(result, ValidationResult)
        assert isinstance(result.passed, bool)
        assert isinstance(result.details, dict)
        assert isinstance(result.status, str)

    def test_empty_pixel_data_with_ocr(self):
        """Empty pixel_data but OCR present → graceful handling."""
        validator = Validator()
        ocr_data = {"amazon": {"current": 3000, "lowest": 1500, "highest": 7000}}

        result = validator.validate({}, ocr_data)

        assert isinstance(result, ValidationResult)

    def test_pixel_data_with_empty_ocr(self):
        """Pixel data present but empty OCR → low_confidence."""
        validator = Validator()
        pixel_data = {"amazon": {"current": 2999, "lowest": 1500, "highest": 7000}}

        result = validator.validate(pixel_data, {})

        assert result.status == "low_confidence"
