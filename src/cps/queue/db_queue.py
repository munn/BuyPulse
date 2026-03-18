# src/cps/queue/db_queue.py
"""PostgreSQL-backed task queue using SELECT FOR UPDATE SKIP LOCKED."""

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import CrawlTask, Product
from cps.queue.protocol import Task

log = structlog.get_logger()


class DbTaskQueue:
    """Task queue backed by the crawl_tasks PostgreSQL table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def pop_next(self, platform: str) -> Task | None:
        """Atomically claim the next pending task for the given platform.

        Uses FOR UPDATE SKIP LOCKED to prevent duplicate processing
        across concurrent workers.
        """
        stmt = (
            select(CrawlTask)
            .where(CrawlTask.status == "pending", CrawlTask.platform == platform)
            .order_by(CrawlTask.priority, CrawlTask.scheduled_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        crawl_task = result.scalar_one_or_none()

        if crawl_task is None:
            return None

        crawl_task.status = "in_progress"
        crawl_task.started_at = datetime.now(timezone.utc)
        await self._session.flush()

        product = await self._session.get(Product, crawl_task.product_id)
        if product is None:
            crawl_task.status = "failed"
            crawl_task.error_message = "Product not found"
            await self._session.flush()
            log.error("product_not_found", task_id=crawl_task.id, product_id=crawl_task.product_id)
            return None

        return Task(
            id=crawl_task.id,
            product_id=crawl_task.product_id,
            platform_id=product.platform_id,
            platform=crawl_task.platform,
        )

    async def complete(self, task_id: int) -> None:
        """Mark a task as completed and schedule the next crawl (7 days)."""
        task = await self._session.get(CrawlTask, task_id)
        if task is None:
            return
        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        task.total_crawls += 1
        task.next_crawl_at = datetime.now(timezone.utc) + timedelta(days=7)
        task.error_message = None
        await self._session.flush()

    async def fail(self, task_id: int, error: str) -> None:
        """Mark a task as failed with retry logic."""
        task = await self._session.get(CrawlTask, task_id)
        if task is None:
            return
        task.retry_count += 1
        task.error_message = error
        if task.retry_count >= task.max_retries:
            task.status = "failed"
        else:
            task.status = "pending"
        await self._session.flush()

    async def requeue(self, task_id: int) -> None:
        """Return a task to pending without incrementing retry count."""
        task = await self._session.get(CrawlTask, task_id)
        if task is None:
            return
        task.status = "pending"
        task.started_at = None
        task.error_message = None
        await self._session.flush()
