"""CrawlTask helpers for on-demand crawl requests (spec Section 7.1)."""
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import CrawlTask


async def upsert_crawl_task(
    session: AsyncSession,
    product_id: int,
    priority: int = 1,
) -> None:
    """Upsert a crawl task: create if not exists, or reset to pending with given priority.

    Per spec: crawl_tasks.product_id has a unique constraint — must use upsert, not insert.
    """
    stmt = pg_insert(CrawlTask).values(
        product_id=product_id,
        priority=priority,
        status="pending",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["product_id"],
        set_={
            "status": "pending",
            "priority": priority,
            "retry_count": 0,
            "error_message": None,
        },
    )
    await session.execute(stmt)
    await session.flush()
