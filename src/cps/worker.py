"""Generic worker loop for continuous crawl processing."""

import asyncio

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from cps.crawler.downloader import (
    BlockedError,
    DownloadError,
    RateLimitError,
    ServerError,
)
from cps.pipeline.result_store import store_results
from cps.platforms.protocol import PlatformFetcher, PlatformParser
from cps.queue.protocol import TaskQueue

log = structlog.get_logger()


class WorkerLoop:
    """Continuously processes crawl tasks for a single platform."""

    def __init__(
        self,
        session: AsyncSession,
        queue: TaskQueue,
        fetcher: PlatformFetcher,
        parser: PlatformParser,
        platform: str,
        idle_sleep: float = 5.0,
        heartbeat=None,
    ) -> None:
        self._session = session
        self._queue = queue
        self._fetcher = fetcher
        self._parser = parser
        self._platform = platform
        self._idle_sleep = idle_sleep
        self._running = True
        self._heartbeat = heartbeat
        self._tasks_completed = 0

    def stop(self) -> None:
        """Signal the worker to stop after the current task."""
        self._running = False

    async def run_once(self) -> bool:
        """Process a single task. Returns True if a task was successfully processed."""
        task = await self._queue.pop_next(self._platform)
        if task is None:
            return False

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
            self._tasks_completed += 1
            if self._heartbeat:
                await self._heartbeat.beat(
                    current_task_id=None,
                    tasks_completed=self._tasks_completed,
                )
            await self._session.commit()
            log.info("task_complete", platform_id=task.platform_id, points=parse_result.points_extracted)
            return True

        except RateLimitError:
            await self._queue.requeue(task.id)
            await self._session.commit()
            log.warning("rate_limited", platform_id=task.platform_id)
            return False

        except BlockedError:
            await self._queue.fail(task.id, "Blocked (403)")
            await self._session.commit()
            log.error("blocked", platform_id=task.platform_id)
            return False

        except (ServerError, DownloadError) as exc:
            await self._queue.fail(task.id, str(exc))
            await self._session.commit()
            log.error("download_error", platform_id=task.platform_id, error=str(exc))
            return False

        except Exception as exc:
            await self._queue.fail(task.id, str(exc))
            await self._session.commit()
            log.error("unexpected_error", platform_id=task.platform_id, error=str(exc))
            return False

    async def run_forever(self) -> None:
        """Main loop — process tasks until stopped."""
        log.info("worker_started", platform=self._platform)

        while self._running:
            processed = await self.run_once()
            if not processed:
                if self._heartbeat:
                    await self._heartbeat.set_idle()
                await asyncio.sleep(self._idle_sleep)

        log.info("worker_stopped", platform=self._platform)
