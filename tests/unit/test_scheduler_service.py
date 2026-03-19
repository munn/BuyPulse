"""Tests for scheduler service — status derivation logic."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_job(*, status="idle", interval_s=300, started_at=None, last_heartbeat=None,
              last_run_at=None, next_run_at=None, last_result=None, error_count=0):
    job = MagicMock()
    job.name = "crawl_scheduler"
    job.status = status
    job.interval_s = interval_s
    job.started_at = started_at
    job.last_heartbeat = last_heartbeat
    job.last_run_at = last_run_at
    job.next_run_at = next_run_at
    job.last_result = last_result
    job.error_count = error_count
    job.updated_at = datetime.now(timezone.utc)
    return job


class TestDeriveProcessStatus:
    def test_running_when_heartbeat_fresh(self):
        from cps.services.scheduler_service import _derive_process_status
        now = datetime.now(timezone.utc)
        started = now - timedelta(hours=1)
        assert _derive_process_status("idle", started, now - timedelta(seconds=60), now, 300) == "running"

    def test_offline_when_status_offline(self):
        from cps.services.scheduler_service import _derive_process_status
        now = datetime.now(timezone.utc)
        assert _derive_process_status("offline", None, None, now, 300) == "offline"

    def test_dead_when_heartbeat_stale(self):
        from cps.services.scheduler_service import _derive_process_status
        now = datetime.now(timezone.utc)
        started = now - timedelta(hours=2)
        stale = now - timedelta(seconds=700)  # > 2 * 300
        assert _derive_process_status("idle", started, stale, now, 300) == "dead"

    def test_offline_when_no_heartbeat_and_not_offline(self):
        from cps.services.scheduler_service import _derive_process_status
        now = datetime.now(timezone.utc)
        assert _derive_process_status("idle", None, None, now, 300) == "offline"

    def test_offline_when_no_started_at(self):
        from cps.services.scheduler_service import _derive_process_status
        now = datetime.now(timezone.utc)
        assert _derive_process_status("idle", None, now, now, 300) == "offline"


class TestGetSchedulerStatus:
    @pytest.mark.anyio
    async def test_returns_status_with_jobs(self):
        from cps.services.scheduler_service import get_scheduler_status
        now = datetime.now(timezone.utc)
        job = _make_job(
            status="idle",
            started_at=now - timedelta(hours=1),
            last_heartbeat=now - timedelta(seconds=30),
            last_run_at=now - timedelta(minutes=5),
            next_run_at=now,
            last_result="rescheduled=12",
        )
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [job]
        mock_session.execute.return_value = mock_result

        status = await get_scheduler_status(mock_session)
        assert status["process"]["status"] == "running"
        assert status["process"]["uptime_seconds"] > 0
        assert len(status["jobs"]) == 1
        assert status["jobs"][0]["name"] == "crawl_scheduler"

    @pytest.mark.anyio
    async def test_returns_offline_when_no_jobs(self):
        from cps.services.scheduler_service import get_scheduler_status
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        status = await get_scheduler_status(mock_session)
        assert status["process"]["status"] == "offline"
        assert len(status["jobs"]) == 0
