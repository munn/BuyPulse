# tests/unit/test_discovery_pipeline.py
"""Tests for ASIN discovery validation pipeline."""

import re
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.discovery.pipeline import DiscoveryPipeline, SubmitResult, validate_platform_id


class TestValidatePlatformId:
    def test_valid_amazon_asin(self):
        assert validate_platform_id("B08N5WRWNW", "amazon") is True

    def test_invalid_amazon_asin_too_short(self):
        assert validate_platform_id("B08N", "amazon") is False

    def test_invalid_amazon_asin_special_chars(self):
        assert validate_platform_id("B08N-WRW!W", "amazon") is False

    def test_unknown_platform_raises(self):
        with pytest.raises(ValueError, match="Unknown platform"):
            validate_platform_id("12345", "ebay")


class TestSubmitResult:
    def test_dataclass_fields(self):
        result = SubmitResult(submitted=10, skipped=3, total=13)
        assert result.submitted == 10
        assert result.skipped == 3


class TestSubmitCandidates:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()
        return session

    async def test_creates_products_and_tasks(self, mock_session):
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        pipeline = DiscoveryPipeline(mock_session)
        result = await pipeline.submit_candidates(
            ["B08N5WRWNW", "B09V3KXJPB"],
            platform="amazon",
        )

        assert result.submitted == 2
        assert result.skipped == 0
        assert result.total == 2

    async def test_skips_existing_products(self, mock_session):
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = ["B08N5WRWNW"]
        mock_session.execute.return_value = mock_result

        pipeline = DiscoveryPipeline(mock_session)
        result = await pipeline.submit_candidates(
            ["B08N5WRWNW", "B09V3KXJPB"],
            platform="amazon",
        )

        assert result.submitted == 1
        assert result.skipped == 1

    async def test_skips_invalid_platform_ids(self, mock_session):
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        pipeline = DiscoveryPipeline(mock_session)
        result = await pipeline.submit_candidates(
            ["B08N5WRWNW", "INVALID", "B09V3KXJPB"],
            platform="amazon",
        )

        assert result.submitted == 2
        assert result.skipped == 1

    async def test_uses_high_priority_for_validation(self, mock_session):
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        pipeline = DiscoveryPipeline(mock_session)
        await pipeline.submit_candidates(
            ["B08N5WRWNW"],
            platform="amazon",
            priority=2,
        )

        assert mock_session.add.call_count >= 2


class TestDeactivateNoDataProducts:
    async def test_deactivates_products_with_zero_points(self):
        mock_session = AsyncMock()

        mock_product = MagicMock()
        mock_product.is_active = True

        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [mock_product]
        mock_session.execute.return_value = mock_result

        pipeline = DiscoveryPipeline(mock_session)
        count = await pipeline.deactivate_no_data_products()

        assert count == 1
        assert mock_product.is_active is False
