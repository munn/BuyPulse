"""Tests for scheduler API routes."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def _make_scheduler_job(status="idle"):
    now = datetime.now(timezone.utc)
    job = MagicMock()
    job.name = "crawl_scheduler"
    job.status = status
    job.interval_s = 300
    job.last_run_at = now - timedelta(minutes=5)
    job.next_run_at = now
    job.last_result = "rescheduled=3"
    job.error_count = 0
    job.started_at = now - timedelta(hours=1)
    job.last_heartbeat = now - timedelta(seconds=30)
    job.updated_at = now
    return job


class TestSchedulerStatus:
    @pytest.mark.anyio
    async def test_returns_status(self, auth_client, mock_db):
        job = _make_scheduler_job()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [job]
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/scheduler/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "process" in data
            assert "jobs" in data
            assert data["process"]["status"] == "running"

    @pytest.mark.anyio
    async def test_requires_auth(self, anon_client):
        async with await anon_client() as client:
            resp = await client.get("/api/v1/scheduler/status")
            assert resp.status_code == 401


class TestSchedulerPause:
    @pytest.mark.anyio
    async def test_pause_job(self, auth_client, mock_db):
        job = _make_scheduler_job(status="idle")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.post(
                "/api/v1/scheduler/jobs/crawl_scheduler/pause",
                headers=CSRF_HEADERS,
            )
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_pause_unknown_job_404(self, auth_client, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.post(
                "/api/v1/scheduler/jobs/unknown_job/pause",
                headers=CSRF_HEADERS,
            )
            assert resp.status_code == 404


class TestSchedulerResume:
    @pytest.mark.anyio
    async def test_resume_job(self, auth_client, mock_db):
        job = _make_scheduler_job(status="paused")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.post(
                "/api/v1/scheduler/jobs/crawl_scheduler/resume",
                headers=CSRF_HEADERS,
            )
            assert resp.status_code == 200


class TestSchedulerTrigger:
    @pytest.mark.anyio
    async def test_trigger_job(self, auth_client, mock_db):
        job = _make_scheduler_job()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = job
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.post(
                "/api/v1/scheduler/jobs/crawl_scheduler/trigger",
                headers=CSRF_HEADERS,
            )
            assert resp.status_code == 200
