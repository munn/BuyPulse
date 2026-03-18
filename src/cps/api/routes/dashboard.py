"""Dashboard routes — overview stats, throughput, workers, recent failures."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.deps import get_current_user, get_db
from cps.api.schemas.dashboard import (
    OverviewStats,
    RecentFailure,
    ThroughputBucket,
    WorkerStatus,
)
from cps.db.models import (
    AdminUser,
    CrawlTask,
    FetchRun,
    PriceHistory,
    Product,
    WorkerHeartbeat,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_HEARTBEAT_TIMEOUT = timedelta(seconds=60)


@router.get("/overview", response_model=OverviewStats)
async def overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Return high-level stats for the dashboard."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_24h = now - timedelta(hours=24)

    products_total = await db.scalar(select(func.count()).select_from(Product)) or 0
    products_today = await db.scalar(
        select(func.count()).select_from(Product).where(Product.first_seen >= today_start)
    ) or 0

    crawled_total = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(CrawlTask.status == "completed")
    ) or 0
    crawled_today = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(
            CrawlTask.status == "completed",
            CrawlTask.completed_at >= today_start,
        )
    ) or 0

    price_records_total = await db.scalar(
        select(func.count()).select_from(PriceHistory)
    ) or 0

    # Success rate last 24h
    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(FetchRun.status == "success").label("success"),
        ).where(FetchRun.created_at >= cutoff_24h)
    )
    row = result.one()
    total_24h, success_24h = row.total, row.success
    success_rate = (success_24h / total_24h * 100) if total_24h > 0 else 0.0

    return OverviewStats(
        products_total=products_total,
        products_today=products_today,
        crawled_total=crawled_total,
        crawled_today=crawled_today,
        success_rate_24h=round(success_rate, 1),
        price_records_total=price_records_total,
    )


@router.get("/throughput", response_model=list[ThroughputBucket])
async def throughput(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
    hours: int = 24,
):
    """Return hourly throughput for the last N hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(
            func.date_trunc("hour", CrawlTask.completed_at).label("hour"),
            func.count().label("count"),
        )
        .where(
            CrawlTask.status == "completed",
            CrawlTask.completed_at >= cutoff,
        )
        .group_by("hour")
        .order_by("hour")
    )
    return [ThroughputBucket(hour=row.hour, count=row.count) for row in result]


@router.get("/workers", response_model=list[WorkerStatus])
async def workers(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Return all worker heartbeat statuses."""
    now = datetime.now(timezone.utc)
    result = await db.execute(select(WorkerHeartbeat))
    heartbeats = result.scalars().all()

    out = []
    for hb in heartbeats:
        # If heartbeat is stale, report as offline
        effective_status = hb.status
        if now - hb.last_heartbeat > _HEARTBEAT_TIMEOUT:
            effective_status = "offline"

        out.append(WorkerStatus(
            worker_id=hb.worker_id,
            platform=hb.platform,
            status=effective_status,
            current_task_id=hb.current_task_id,
            tasks_completed=hb.tasks_completed,
            last_heartbeat=hb.last_heartbeat,
            started_at=hb.started_at,
        ))
    return out


@router.get("/recent-failures", response_model=list[RecentFailure])
async def recent_failures(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Return top 20 recent failed crawl tasks."""
    result = await db.execute(
        select(CrawlTask, Product.platform_id)
        .join(Product, CrawlTask.product_id == Product.id)
        .where(CrawlTask.status == "failed")
        .order_by(CrawlTask.updated_at.desc())
        .limit(20)
    )
    rows = result.all()
    return [
        RecentFailure(
            task_id=task.id,
            platform_id=pid,
            platform=task.platform,
            error_message=task.error_message,
            updated_at=task.updated_at,
        )
        for task, pid in rows
    ]
