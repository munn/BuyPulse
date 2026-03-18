"""Tests for result_store — FetchRun creation, PriceHistory insert, PriceSummary upsert."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.pipeline.result_store import _build_price_summary_upsert, store_results
from cps.platforms.protocol import ParseResult, PriceRecord, PriceSummaryData


class TestBuildPriceSummaryUpsert:
    def test_generates_on_conflict_sql(self):
        from sqlalchemy.dialects import postgresql

        stmt = _build_price_summary_upsert(
            product_id=1,
            price_type="amazon",
            lowest_price=16900,
            lowest_date=None,
            highest_price=24900,
            highest_date=None,
            current_price=18900,
            current_date=None,
            extraction_id=1,
        )
        compiled = str(stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        ))
        assert "ON CONFLICT" in compiled.upper() or "on conflict" in compiled.lower()


class TestStoreResults:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock()
        session.begin_nested = MagicMock()
        return session

    async def test_creates_fetch_run(self, mock_session):
        parse_result = ParseResult(
            records=[],
            points_extracted=0,
            confidence=0.5,
            validation_passed=False,
            validation_status="failed",
        )

        async def set_id():
            for call in mock_session.add.call_args_list:
                obj = call[0][0]
                if hasattr(obj, "product_id") and hasattr(obj, "chart_path"):
                    obj.id = 1
        mock_session.flush.side_effect = set_id

        run_id = await store_results(mock_session, product_id=42, parse_result=parse_result)
        assert mock_session.add.called

    async def test_stores_price_records(self, mock_session):
        records = [
            PriceRecord("amazon", date(2025, 1, 1), 29900, "ccc_chart"),
            PriceRecord("amazon", date(2025, 2, 1), 24900, "ccc_chart"),
        ]
        parse_result = ParseResult(
            records=records,
            points_extracted=2,
            validation_status="success",
        )

        nested_cm = AsyncMock()
        nested_cm.__aenter__ = AsyncMock()
        nested_cm.__aexit__ = AsyncMock(return_value=False)
        mock_session.begin_nested.return_value = nested_cm

        async def set_id():
            for call in mock_session.add.call_args_list:
                obj = call[0][0]
                if hasattr(obj, "chart_path"):
                    obj.id = 1
        mock_session.flush.side_effect = set_id

        await store_results(mock_session, product_id=42, parse_result=parse_result)
        assert mock_session.add.call_count >= 3
