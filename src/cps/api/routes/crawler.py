"""Crawler routes — task queue, enqueue, retry, stats."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.deps import get_current_user, get_db, log_audit
from cps.api.schemas.common import PaginatedResponse
from cps.api.schemas.crawl import (
    BatchRetryRequest,
    CrawlStats,
    CrawlTaskItem,
    EnqueueRequest,
)
from cps.db.models import AdminUser, CrawlTask, Product

router = APIRouter(prefix="/crawler", tags=["crawler"])


@router.get("/tasks", response_model=PaginatedResponse[CrawlTaskItem])
async def list_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    platform: str | None = None,
):
    """List crawl tasks with filters."""
    query = (
        select(CrawlTask, Product.platform_id.label("pid"))
        .join(Product, CrawlTask.product_id == Product.id)
    )
    count_query = select(func.count()).select_from(CrawlTask)

    if status:
        query = query.where(CrawlTask.status == status)
        count_query = count_query.where(CrawlTask.status == status)
    if platform:
        query = query.where(CrawlTask.platform == platform)
        count_query = count_query.where(CrawlTask.platform == platform)

    total = await db.scalar(count_query) or 0
    offset = (page - 1) * page_size

    result = await db.execute(
        query.order_by(CrawlTask.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    items = []
    for task, pid in result.all():
        item = CrawlTaskItem(
            id=task.id,
            product_id=task.product_id,
            platform_id=pid,
            platform=task.platform,
            status=task.status,
            priority=task.priority,
            retry_count=task.retry_count,
            error_message=task.error_message,
            started_at=task.started_at,
            completed_at=task.completed_at,
            updated_at=task.updated_at,
        )
        items.append(item)

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/enqueue")
async def enqueue(
    body: EnqueueRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Add ASINs to crawl queue."""
    from cps.services.crawl_service import upsert_crawl_task

    enqueued = 0
    for pid in body.platform_ids:
        # Look up product
        result = await db.execute(
            select(Product).where(
                Product.platform_id == pid,
                Product.platform == body.platform,
            )
        )
        product = result.scalar_one_or_none()
        if product:
            await upsert_crawl_task(db, product.id)
            enqueued += 1

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "trigger", "crawl_task", client_ip,
                    details={"enqueued": enqueued, "total": len(body.platform_ids)})
    await db.commit()
    return {"enqueued": enqueued}


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Retry a single failed task."""
    result = await db.execute(
        update(CrawlTask)
        .where(CrawlTask.id == task_id, CrawlTask.status == "failed")
        .values(status="pending", error_message=None, retry_count=0)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Task not found or not failed")

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "trigger", "crawl_task", client_ip,
                    resource_id=str(task_id))
    await db.commit()
    return {"detail": "Task queued for retry"}


@router.post("/tasks/batch-retry")
async def batch_retry(
    body: BatchRetryRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Batch retry failed tasks (max 500)."""
    result = await db.execute(
        update(CrawlTask)
        .where(CrawlTask.id.in_(body.ids), CrawlTask.status == "failed")
        .values(status="pending", error_message=None, retry_count=0)
    )

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "trigger", "crawl_task", client_ip,
                    details={"retried": result.rowcount, "requested": len(body.ids)})
    await db.commit()
    return {"retried": result.rowcount}


@router.post("/retry-all-failed")
async def retry_all_failed(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Retry all failed tasks (max 10,000)."""
    # Get IDs first to cap at 10k
    id_result = await db.execute(
        select(CrawlTask.id)
        .where(CrawlTask.status == "failed")
        .limit(10000)
    )
    ids = [row[0] for row in id_result.all()]

    if ids:
        result = await db.execute(
            update(CrawlTask)
            .where(CrawlTask.id.in_(ids))
            .values(status="pending", error_message=None, retry_count=0)
        )
        retried = result.rowcount
    else:
        retried = 0

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "trigger", "crawl_task", client_ip,
                    details={"retried": retried})
    await db.commit()
    return {"retried": retried}


@router.get("/stats", response_model=CrawlStats)
async def stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Crawl statistics overview."""
    pending = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(CrawlTask.status == "pending")
    ) or 0
    running = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(CrawlTask.status == "running")
    ) or 0
    completed = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(CrawlTask.status == "completed")
    ) or 0
    failed = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(CrawlTask.status == "failed")
    ) or 0

    # Speed: completions in last 24h
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    completed_24h = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(
            CrawlTask.status == "completed",
            CrawlTask.completed_at >= cutoff,
        )
    ) or 0
    speed = completed_24h / 24.0

    return CrawlStats(
        pending=pending, running=running, completed=completed,
        failed=failed, speed_per_hour=round(speed, 1),
    )
