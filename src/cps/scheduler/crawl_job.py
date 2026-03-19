"""Crawl rescheduling tick — resets due completed tasks to pending.

Migrated from jobs/crawl_scheduler.py. Runs as part of the independent
Scheduler process (not inside Telegram Bot).

Spec Section 3.1 + Section 6.3.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import CrawlTask

log = structlog.get_logger()

_BATCH_LIMIT = 50


@dataclass(frozen=True)
class TickResult:
    """Immutable result of a single scheduler tick."""
    rescheduled: int


async def crawl_scheduler_tick(session: AsyncSession) -> TickResult:
    """Find completed tasks past their next_crawl_at and reset to pending.

    Returns the number of tasks rescheduled.
    """
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(CrawlTask).where(
            CrawlTask.status == "completed",
            CrawlTask.next_crawl_at <= now,
        ).limit(_BATCH_LIMIT)
    )
    tasks = list(result.scalars().all())

    for task in tasks:
        task.status = "pending"
        task.retry_count = 0
        task.error_message = None

    if tasks:
        await session.flush()

    log.info("crawl_scheduler_tick_complete", rescheduled=len(tasks))
    return TickResult(rescheduled=len(tasks))
