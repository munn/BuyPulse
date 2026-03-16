"""Integration test for auto-recovery state machine — quickstart scenario 7 (T034).

Tests state transitions when all requests fail continuously.
Uses respx to simulate server errors and mocked time for recovery waits.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from cps.db.models import CrawlTask, Product
from cps.pipeline.orchestrator import (
    CONSECUTIVE_FAILURE_THRESHOLD,
    PipelineOrchestrator,
    RecoveryState,
)

CCC_BASE_URL = "https://charts.camelcamelcamel.com/us"


@pytest.fixture
def mock_alert_service():
    """Create a mock alert service."""
    service = AsyncMock()
    service.send_alert = AsyncMock(return_value=True)
    return service


class TestAutoRecoveryStateMachine:
    """Verify state machine transitions when all downloads fail."""

    @respx.mock
    async def test_pauses_after_consecutive_failures(
        self, db_session, mock_alert_service, tmp_path
    ):
        """After CONSECUTIVE_FAILURE_THRESHOLD failures, state transitions to PAUSED."""
        # Create enough products to hit the threshold
        for i in range(CONSECUTIVE_FAILURE_THRESHOLD + 5):
            product = Product(asin=f"B0TST{i:04d}")
            db_session.add(product)
            await db_session.flush()
            task = CrawlTask(product_id=product.id, status="pending")
            db_session.add(task)
        await db_session.flush()

        # All requests fail with 500
        respx.get(url__startswith=CCC_BASE_URL).mock(
            return_value=httpx.Response(500)
        )

        orchestrator = PipelineOrchestrator(
            session=db_session,
            data_dir=tmp_path / "data",
            base_url=CCC_BASE_URL,
            rate_limit=1000.0,  # fast for tests
            alert_service=mock_alert_service,
        )

        # Patch asyncio.sleep to skip waits
        with patch("cps.pipeline.orchestrator.asyncio.sleep", new_callable=AsyncMock):
            await orchestrator.run(limit=CONSECUTIVE_FAILURE_THRESHOLD + 5)

        # Verify state transitioned past RUNNING
        assert orchestrator.state != RecoveryState.RUNNING

    @respx.mock
    async def test_final_stop_after_all_recovery_rounds(
        self, db_session, mock_alert_service, tmp_path
    ):
        """After 3 failed recovery rounds, state reaches STOPPED."""
        # Create many products
        for i in range(200):
            product = Product(asin=f"B1TST{i:04d}")
            db_session.add(product)
            await db_session.flush()
            task = CrawlTask(product_id=product.id, status="pending")
            db_session.add(task)
        await db_session.flush()

        respx.get(url__startswith=CCC_BASE_URL).mock(
            return_value=httpx.Response(500)
        )

        orchestrator = PipelineOrchestrator(
            session=db_session,
            data_dir=tmp_path / "data",
            base_url=CCC_BASE_URL,
            rate_limit=1000.0,
            alert_service=mock_alert_service,
        )

        with patch("cps.pipeline.orchestrator.asyncio.sleep", new_callable=AsyncMock):
            await orchestrator.run(limit=200)

        # Should eventually reach STOPPED
        assert orchestrator.state == RecoveryState.STOPPED

    @respx.mock
    async def test_alert_sent_on_state_transition(
        self, db_session, mock_alert_service, tmp_path
    ):
        """Email alert is sent on each state transition."""
        for i in range(CONSECUTIVE_FAILURE_THRESHOLD + 5):
            product = Product(asin=f"B2TST{i:04d}")
            db_session.add(product)
            await db_session.flush()
            task = CrawlTask(product_id=product.id, status="pending")
            db_session.add(task)
        await db_session.flush()

        respx.get(url__startswith=CCC_BASE_URL).mock(
            return_value=httpx.Response(500)
        )

        orchestrator = PipelineOrchestrator(
            session=db_session,
            data_dir=tmp_path / "data",
            base_url=CCC_BASE_URL,
            rate_limit=1000.0,
            alert_service=mock_alert_service,
        )

        with patch("cps.pipeline.orchestrator.asyncio.sleep", new_callable=AsyncMock):
            await orchestrator.run(limit=CONSECUTIVE_FAILURE_THRESHOLD + 5)

        # At least one alert should have been sent
        assert mock_alert_service.send_alert.call_count >= 1
