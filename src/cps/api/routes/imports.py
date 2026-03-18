"""Import routes — job list and progress."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.deps import get_current_user, get_db
from cps.api.schemas.import_ import ImportJobItem
from cps.db.models import AdminUser, ImportJob

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("", response_model=list[ImportJobItem])
async def list_imports(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """List all import jobs (most recent first)."""
    result = await db.execute(
        select(ImportJob).order_by(ImportJob.created_at.desc()).limit(50)
    )
    return [ImportJobItem.model_validate(j) for j in result.scalars().all()]


@router.get("/{job_id}", response_model=ImportJobItem)
async def get_import(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Get import job progress."""
    result = await db.execute(
        select(ImportJob).where(ImportJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return ImportJobItem.model_validate(job)
