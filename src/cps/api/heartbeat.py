"""Worker heartbeat service — registers and updates heartbeat in DB."""

import os
import socket
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import WorkerHeartbeat


class HeartbeatService:
    """Manages heartbeat registration and updates for a single worker."""

    def __init__(self, session: AsyncSession, platform: str) -> None:
        self._session = session
        self._platform = platform
        self._worker_id: str | None = None

    @property
    def worker_id(self) -> str | None:
        return self._worker_id

    @staticmethod
    def _make_worker_id(platform: str) -> str:
        hostname = socket.gethostname()
        pid = os.getpid()
        return f"{platform}-{hostname}-{pid}"

    async def register(self) -> str:
        self._worker_id = self._make_worker_id(self._platform)
        hb = WorkerHeartbeat(
            worker_id=self._worker_id,
            platform=self._platform,
            status="online",
        )
        self._session.add(hb)
        await self._session.flush()
        return self._worker_id

    async def beat(self, current_task_id: int | None = None,
                   tasks_completed: int = 0, status: str = "online") -> None:
        if self._worker_id is None:
            return
        await self._session.execute(
            update(WorkerHeartbeat)
            .where(WorkerHeartbeat.worker_id == self._worker_id)
            .values(
                last_heartbeat=datetime.now(timezone.utc),
                current_task_id=current_task_id,
                tasks_completed=tasks_completed,
                status=status,
            )
        )

    async def set_idle(self) -> None:
        await self.beat(current_task_id=None, status="idle")

    async def set_offline(self) -> None:
        if self._worker_id is None:
            return
        await self._session.execute(
            update(WorkerHeartbeat)
            .where(WorkerHeartbeat.worker_id == self._worker_id)
            .values(status="offline", current_task_id=None,
                    last_heartbeat=datetime.now(timezone.utc))
        )
