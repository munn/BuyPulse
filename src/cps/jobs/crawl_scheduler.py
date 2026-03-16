"""Periodic job: schedule re-crawls for monitored ASINs.

Runs every 5 minutes. Picks products whose crawl_task.next_crawl_at has passed
and resets them to pending for the pipeline to pick up.
"""
import structlog
from datetime import datetime, timezone

from sqlalchemy import select
from telegram.ext import ContextTypes

from cps.db.models import CrawlTask
from cps.db.session import get_session

log = structlog.get_logger()


async def crawl_scheduler_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called by JobQueue every 5 minutes."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        now = datetime.now(timezone.utc)

        # Find completed tasks whose next_crawl_at has passed
        result = await session.execute(
            select(CrawlTask).where(
                CrawlTask.status == "completed",
                CrawlTask.next_crawl_at <= now,
            ).limit(50)
        )
        tasks = list(result.scalars().all())

        for task in tasks:
            task.status = "pending"
            task.retry_count = 0
            task.error_message = None

        if tasks:
            await session.flush()
            await session.commit()

        log.info("crawl_scheduler_complete", rescheduled=len(tasks))
