"""Tests for SchedulerLoop — tick model, pause check, error handling."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


def _make_scheduler_job(status="idle"):
    from cps.db.models import SchedulerJob
    job = MagicMock(spec=SchedulerJob)
    job.name = "crawl_scheduler"
    job.status = status
    job.interval_s = 300
    job.last_heartbeat = datetime.now(timezone.utc)
    job.started_at = datetime.now(timezone.utc)
    job.error_count = 0
    job.updated_at = datetime.now(timezone.utc)
    return job


class TestSchedulerLoopTick:
    @pytest.mark.anyio
    async def test_tick_calls_crawl_job_and_commits(self):
        from cps.scheduler.loop import SchedulerLoop

        session = _make_mock_session()
        job = _make_scheduler_job(status="idle")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        session.execute.return_value = mock_result

        loop = SchedulerLoop(session)

        with patch("cps.scheduler.loop.crawl_scheduler_tick") as mock_tick:
            from cps.scheduler.crawl_job import TickResult
            mock_tick.return_value = TickResult(rescheduled=5)
            await loop.tick()
            mock_tick.assert_called_once_with(session)
            session.commit.assert_called_once()
            assert job.status == "idle"
            assert job.last_result == "rescheduled=5"
            assert job.last_run_at is not None

    @pytest.mark.anyio
    async def test_tick_skips_when_paused(self):
        from cps.scheduler.loop import SchedulerLoop

        session = _make_mock_session()
        job = _make_scheduler_job(status="paused")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        session.execute.return_value = mock_result

        loop = SchedulerLoop(session)

        with patch("cps.scheduler.loop.crawl_scheduler_tick") as mock_tick:
            await loop.tick()
            mock_tick.assert_not_called()
            session.commit.assert_not_called()

    @pytest.mark.anyio
    async def test_tick_handles_exception_gracefully(self):
        from cps.scheduler.loop import SchedulerLoop

        session = _make_mock_session()
        job = _make_scheduler_job(status="idle")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        session.execute.return_value = mock_result

        loop = SchedulerLoop(session)

        with patch("cps.scheduler.loop.crawl_scheduler_tick", side_effect=RuntimeError("test")):
            await loop.tick()
            assert job.status == "error"
            assert job.error_count == 1


class TestSchedulerLoopStop:
    @pytest.mark.anyio
    async def test_stop_signals_loop_to_exit(self):
        from cps.scheduler.loop import SchedulerLoop

        session = _make_mock_session()
        loop = SchedulerLoop(session, tick_interval=0.1, startup_delay=0.0)
        loop.stop()
        await loop.run_forever()
