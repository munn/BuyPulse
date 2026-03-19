"""Scheduler API routes — status, trigger, pause, resume.

Spec Section 8.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.deps import get_current_user, get_db, log_audit
from cps.api.schemas.scheduler import SchedulerStatusResponse
from cps.db.models import AdminUser, SchedulerJob
from cps.services.scheduler_service import get_scheduler_status

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status", response_model=SchedulerStatusResponse)
async def status(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    return await get_scheduler_status(db)


async def _get_job(db: AsyncSession, name: str) -> SchedulerJob:
    result = await db.execute(
        select(SchedulerJob).where(SchedulerJob.name == name)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{name}' not found")
    return job


@router.post("/jobs/{name}/trigger")
async def trigger_job(
    name: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    job = await _get_job(db, name)
    now = datetime.now(timezone.utc)
    job.next_run_at = now
    job.updated_at = now
    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "trigger", "scheduler_job", client_ip,
                    resource_id=name)
    await db.commit()
    return {"detail": f"Job '{name}' triggered"}


@router.post("/jobs/{name}/pause")
async def pause_job(
    name: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    job = await _get_job(db, name)
    now = datetime.now(timezone.utc)
    job.status = "paused"
    job.updated_at = now
    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "pause", "scheduler_job", client_ip,
                    resource_id=name)
    await db.commit()
    return {"detail": f"Job '{name}' paused"}


@router.post("/jobs/{name}/resume")
async def resume_job(
    name: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    job = await _get_job(db, name)
    now = datetime.now(timezone.utc)
    job.status = "idle"
    job.updated_at = now
    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "resume", "scheduler_job", client_ip,
                    resource_id=name)
    await db.commit()
    return {"detail": f"Job '{name}' resumed"}
