"""Integration test for auto-recovery state machine — quickstart scenario 7 (T034).

Tests state transitions when all requests fail continuously.
Mocks CccDownloader.download to simulate server errors.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from cps.crawler.downloader import ServerError
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

    async def test_pauses_after_consecutive_failures(
        self, db_session, mock_alert_service, tmp_path
    ):
        """After CONSECUTIVE_FAILURE_THRESHOLD failures, state transitions to PAUSED."""
        # Create enough products to hit the threshold
        for i in range(CONSECUTIVE_FAILURE_THRESHOLD + 5):
            product = Product(platform_id=f"B0TST{i:04d}")
            db_session.add(product)
            await db_session.flush()
            task = CrawlTask(product_id=product.id, status="pending")
            db_session.add(task)
        await db_session.flush()

        orchestrator = PipelineOrchestrator(
            session=db_session,
            data_dir=tmp_path / "data",
            base_url=CCC_BASE_URL,
            rate_limit=1000.0,  # fast for tests
            alert_service=mock_alert_service,
        )

        # Mock downloader to always raise ServerError
        orchestrator._downloader.download = AsyncMock(
            side_effect=ServerError("Server error (500)")
        )

        # Patch asyncio.sleep to skip waits
        with patch("cps.pipeline.orchestrator.asyncio.sleep", new_callable=AsyncMock):
            await orchestrator.run(limit=CONSECUTIVE_FAILURE_THRESHOLD + 5)

        # Verify state transitioned past RUNNING
        assert orchestrator.state != RecoveryState.RUNNING

    async def test_final_stop_after_all_recovery_rounds(
        self, db_session, mock_alert_service, tmp_path
    ):
        """After 3 failed recovery rounds, state reaches STOPPED."""
        for i in range(250):
            product = Product(platform_id=f"B1TST{i:04d}")
            db_session.add(product)
            await db_session.flush()
            task = CrawlTask(product_id=product.id, status="pending")
            db_session.add(task)
        await db_session.flush()

        orchestrator = PipelineOrchestrator(
            session=db_session,
            data_dir=tmp_path / "data",
            base_url=CCC_BASE_URL,
            rate_limit=1000.0,
            alert_service=mock_alert_service,
        )

        orchestrator._downloader.download = AsyncMock(
            side_effect=ServerError("Server error (500)")
        )

        with patch("cps.pipeline.orchestrator.asyncio.sleep", new_callable=AsyncMock):
            await orchestrator.run(limit=250)

        # Should eventually reach STOPPED
        assert orchestrator.state == RecoveryState.STOPPED

    async def test_alert_sent_on_state_transition(
        self, db_session, mock_alert_service, tmp_path
    ):
        """Email alert is sent on each state transition."""
        for i in range(CONSECUTIVE_FAILURE_THRESHOLD + 5):
            product = Product(platform_id=f"B2TST{i:04d}")
            db_session.add(product)
            await db_session.flush()
            task = CrawlTask(product_id=product.id, status="pending")
            db_session.add(task)
        await db_session.flush()

        orchestrator = PipelineOrchestrator(
            session=db_session,
            data_dir=tmp_path / "data",
            base_url=CCC_BASE_URL,
            rate_limit=1000.0,
            alert_service=mock_alert_service,
        )

        orchestrator._downloader.download = AsyncMock(
            side_effect=ServerError("Server error (500)")
        )

        with patch("cps.pipeline.orchestrator.asyncio.sleep", new_callable=AsyncMock):
            await orchestrator.run(limit=CONSECUTIVE_FAILURE_THRESHOLD + 5)

        # At least one alert should have been sent
        assert mock_alert_service.send_alert.call_count >= 1
