"""Pipeline orchestrator — batch processing with auto-recovery state machine."""

import asyncio
import enum
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.alerts.email import AlertService
from cps.crawler.downloader import (
    BlockedError,
    DownloadError,
    RateLimitError,
    ServerError,
)
from cps.db.models import CrawlTask
from cps.pipeline.result_store import store_results
from cps.platforms.protocol import PlatformFetcher, PlatformParser
from cps.queue.protocol import Task, TaskQueue

log = structlog.get_logger()


class RecoveryState(enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    RECOVERING_1 = "recovering_1"
    PAUSED_2 = "paused_2"
    RECOVERING_2 = "recovering_2"
    PAUSED_3 = "paused_3"
    RECOVERING_3 = "recovering_3"
    STOPPED = "stopped"


_RECOVERY_TRANSITIONS = {
    RecoveryState.PAUSED: (3600, RecoveryState.RECOVERING_1),
    RecoveryState.PAUSED_2: (21600, RecoveryState.RECOVERING_2),
    RecoveryState.PAUSED_3: (86400, RecoveryState.RECOVERING_3),
}

_FAILURE_TRANSITIONS = {
    RecoveryState.RUNNING: RecoveryState.PAUSED,
    RecoveryState.RECOVERING_1: RecoveryState.PAUSED_2,
    RecoveryState.RECOVERING_2: RecoveryState.PAUSED_3,
    RecoveryState.RECOVERING_3: RecoveryState.STOPPED,
}

CONSECUTIVE_FAILURE_THRESHOLD = 50


class PipelineOrchestrator:
    """Batch-process crawl tasks with auto-recovery.

    Uses protocol-based Fetcher/Parser for platform extensibility
    and TaskQueue for safe concurrent task consumption.
    """

    def __init__(
        self,
        session: AsyncSession,
        queue: TaskQueue,
        fetcher: PlatformFetcher,
        parser: PlatformParser,
        platform: str = "amazon",
        alert_service: AlertService | None = None,
    ) -> None:
        self._session = session
        self._queue = queue
        self._fetcher = fetcher
        self._parser = parser
        self._platform = platform
        self._alert_service = alert_service

        self._state = RecoveryState.RUNNING
        self._consecutive_failures = 0

    @property
    def state(self) -> RecoveryState:
        return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    async def run(self, limit: int = 10) -> dict:
        """Process up to `limit` pending crawl tasks.

        Pops tasks one at a time via TaskQueue (FOR UPDATE SKIP LOCKED).
        Returns summary dict with counts.
        """
        succeeded = 0
        failed = 0
        total = 0

        for _ in range(limit):
            if self._state == RecoveryState.STOPPED:
                log.warning("pipeline_stopped", processed=total)
                break

            if (
                self._state in _FAILURE_TRANSITIONS
                and self._consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD
            ):
                await self._transition_to_failure()
                if self._state == RecoveryState.STOPPED:
                    break
                wait_secs, next_state = _RECOVERY_TRANSITIONS[self._state]
                log.info("recovery_waiting", state=self._state.value, wait_secs=wait_secs)
                await asyncio.sleep(wait_secs)
                self._state = next_state
                self._consecutive_failures = 0
                log.info("recovery_resuming", state=self._state.value)

            task = await self._queue.pop_next(self._platform)
            if task is None:
                break

            total += 1
            success = await self._process_one(task)
            await self._session.commit()

            if success:
                succeeded += 1
                self._consecutive_failures = 0
                if self._state != RecoveryState.RUNNING:
                    self._state = RecoveryState.RUNNING
                    log.info("recovery_success", msg="Back to full speed")
            else:
                failed += 1
                self._consecutive_failures += 1

        return {"succeeded": succeeded, "failed": failed, "total": total}

    async def _process_one(self, task: Task) -> bool:
        """Process a single crawl task. Returns True on success."""
        try:
            fetch_result = await self._fetcher.fetch(task.platform_id)
            parse_result = self._parser.parse(fetch_result)

            await store_results(
                self._session,
                task.product_id,
                parse_result,
                chart_path=fetch_result.storage_path,
                platform=task.platform,
            )

            await self._queue.complete(task.id)
            log.info(
                "crawl_success",
                platform_id=task.platform_id,
                points=parse_result.points_extracted,
            )
            return True

        except RateLimitError:
            await self._queue.requeue(task.id)
            log.warning("rate_limited", platform_id=task.platform_id)
            return False

        except BlockedError:
            await self._queue.fail(task.id, "Blocked (403)")
            log.error("blocked", platform_id=task.platform_id)
            return False

        except (ServerError, DownloadError) as exc:
            await self._queue.fail(task.id, str(exc))
            log.error("download_error", platform_id=task.platform_id, error=str(exc))
            return False

        except Exception as exc:
            await self._queue.fail(task.id, str(exc))
            log.error("unexpected_error", platform_id=task.platform_id, error=str(exc))
            return False

    async def _transition_to_failure(self) -> None:
        """Transition to the next failure state."""
        next_state = _FAILURE_TRANSITIONS.get(self._state)
        if next_state is None:
            return

        old_state = self._state
        self._state = next_state
        self._consecutive_failures = 0

        log.warning(
            "state_transition",
            from_state=old_state.value,
            to_state=next_state.value,
        )

        if self._alert_service:
            severity = "CRITICAL" if next_state == RecoveryState.STOPPED else "WARNING"
            await self._alert_service.send_alert(
                severity=severity,
                title=f"Pipeline {next_state.value}",
                body=f"Auto-recovery: {old_state.value} → {next_state.value}. "
                f"Consecutive failures reached threshold.",
            )

    @staticmethod
    async def recover_stale_tasks(
        session: AsyncSession,
        stale_threshold_hours: int = 1,
    ) -> int:
        """Reset stale in_progress tasks to pending (crash recovery)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_threshold_hours)

        result = await session.execute(
            select(CrawlTask).where(
                CrawlTask.status == "in_progress",
                CrawlTask.started_at < cutoff,
            )
        )
        stale_tasks = list(result.scalars().all())

        for task in stale_tasks:
            task.status = "pending"
            task.started_at = None
            log.info(
                "stale_task_reset",
                task_id=task.id,
                retry_count=task.retry_count,
            )

        if stale_tasks:
            await session.flush()
            log.info("crash_recovery_complete", count=len(stale_tasks))

        return len(stale_tasks)
