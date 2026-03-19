"""SchedulerLoop — stateless tick model with error recovery.

Spec Section 3 (Internals) + Section 7 (Error Handling).
"""

import asyncio
import random
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import SchedulerJob
from cps.scheduler.crawl_job import crawl_scheduler_tick

log = structlog.get_logger()

_JOB_NAME = "crawl_scheduler"
_MAX_DB_RETRIES = 3
_RETRY_BASE_SECONDS = 2
_TICK_TIMEOUT_SECONDS = 30


class SchedulerLoop:
    """Tick-based scheduler loop. Mirrors WorkerLoop pattern."""

    def __init__(
        self,
        session: AsyncSession,
        tick_interval: float = 300.0,
        startup_delay: float | None = None,
    ) -> None:
        self._session = session
        self._tick_interval = tick_interval
        self._startup_delay = startup_delay  # None = random 1-5s, 0.0 = no delay (tests)
        self._running = True

    def stop(self) -> None:
        """Signal the loop to stop after the current tick."""
        self._running = False

    async def register(self) -> None:
        """Mark scheduler as online on startup. Caller must commit."""
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(SchedulerJob)
            .where(SchedulerJob.name == _JOB_NAME)
            .values(status="idle", started_at=now, last_heartbeat=now, updated_at=now)
        )
        await self._session.flush()
        log.info("scheduler_registered", job=_JOB_NAME)

    async def set_offline(self) -> None:
        """Mark scheduler as offline on shutdown. Caller must commit."""
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(SchedulerJob)
            .where(SchedulerJob.name == _JOB_NAME)
            .values(status="offline", updated_at=now)
        )
        await self._session.flush()
        log.info("scheduler_offline", job=_JOB_NAME)

    async def tick(self) -> None:
        """Execute one scheduler tick."""
        # Step 1: Read job status — skip if paused
        result = await self._session.execute(
            select(SchedulerJob).where(SchedulerJob.name == _JOB_NAME)
        )
        job = result.scalar_one_or_none()
        if job is None:
            log.error("scheduler_job_not_found", job=_JOB_NAME)
            return

        if job.status == "paused":
            log.info("scheduler_tick_skipped", reason="paused")
            return

        # Spec 3.2: 30s statement_timeout per tick
        await self._session.execute(
            text(f"SET LOCAL statement_timeout = '{_TICK_TIMEOUT_SECONDS}s'")
        )

        now = datetime.now(timezone.utc)
        try:
            job.status = "running"
            await self._session.flush()

            tick_result = await crawl_scheduler_tick(self._session)

            job.status = "idle"
            job.last_run_at = now
            job.next_run_at = datetime.fromtimestamp(
                now.timestamp() + self._tick_interval, tz=timezone.utc
            )
            job.last_result = f"rescheduled={tick_result.rescheduled}"
            job.last_heartbeat = now
            job.error_count = 0
            job.updated_at = now
            await self._session.commit()

        except OperationalError as exc:
            log.error("scheduler_db_error", error=str(exc))
            await self._retry_with_backoff()

        except Exception as exc:
            log.error("scheduler_tick_error", error=str(exc))
            try:
                job.status = "error"
                job.error_count = (job.error_count or 0) + 1
                job.last_heartbeat = now
                job.updated_at = now
                await self._session.commit()
            except Exception:
                pass

    async def _retry_with_backoff(self) -> None:
        """Exponential backoff for DB connection errors."""
        for attempt in range(1, _MAX_DB_RETRIES + 1):
            wait = _RETRY_BASE_SECONDS ** attempt
            log.warning("scheduler_db_retry", attempt=attempt, wait_seconds=wait)
            await asyncio.sleep(wait)
            try:
                await self._session.execute(
                    select(SchedulerJob).where(SchedulerJob.name == _JOB_NAME)
                )
                log.info("scheduler_db_reconnected", attempt=attempt)
                return
            except OperationalError:
                continue
        log.critical("scheduler_db_failed", msg="Exiting after max retries")
        self._running = False

    async def run_forever(self) -> None:
        """Main loop — tick at fixed interval until stopped."""
        log.info("scheduler_started", interval=self._tick_interval)

        if self._startup_delay is None:
            delay = random.uniform(1.0, 5.0)
        else:
            delay = self._startup_delay
        if delay > 0:
            log.info("scheduler_startup_delay", seconds=round(delay, 1))
            await asyncio.sleep(delay)

        while self._running:
            await self.tick()
            if self._running:
                await asyncio.sleep(self._tick_interval)

        log.info("scheduler_stopped")
