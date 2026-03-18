"""Tests for worker heartbeat service."""

import os
import socket
from unittest.mock import AsyncMock

from cps.api.heartbeat import HeartbeatService


class TestHeartbeatService:
    def test_generate_worker_id(self):
        worker_id = HeartbeatService._make_worker_id("amazon")
        assert worker_id.startswith("amazon-")
        assert str(os.getpid()) in worker_id

    async def test_register_creates_heartbeat_row(self):
        mock_session = AsyncMock()
        svc = HeartbeatService(mock_session, "amazon")
        await svc.register()
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        assert svc.worker_id is not None

    async def test_beat_updates_last_heartbeat(self):
        mock_session = AsyncMock()
        svc = HeartbeatService(mock_session, "amazon")
        svc._worker_id = "amazon-test-123"
        await svc.beat(current_task_id=42, tasks_completed=10)
        mock_session.execute.assert_awaited_once()

    async def test_set_offline(self):
        mock_session = AsyncMock()
        svc = HeartbeatService(mock_session, "amazon")
        svc._worker_id = "amazon-test-123"
        await svc.set_offline()
        mock_session.execute.assert_awaited_once()

    async def test_set_idle(self):
        mock_session = AsyncMock()
        svc = HeartbeatService(mock_session, "amazon")
        svc._worker_id = "amazon-test-123"
        await svc.set_idle()
        mock_session.execute.assert_awaited_once()
