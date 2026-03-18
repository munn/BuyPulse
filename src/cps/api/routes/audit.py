"""Audit routes — read-only audit log."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.deps import get_current_user, get_db
from cps.api.schemas.audit import AuditLogItem
from cps.api.schemas.common import PaginatedResponse
from cps.db.models import AdminUser, AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=PaginatedResponse[AuditLogItem])
async def list_audit(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str | None = None,
    resource_type: str | None = None,
):
    """List audit log entries with filters."""
    query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)

    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
        count_query = count_query.where(AuditLog.resource_type == resource_type)

    total = await db.scalar(count_query) or 0
    offset = (page - 1) * page_size

    result = await db.execute(
        query.order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = [AuditLogItem.model_validate(row) for row in result.scalars().all()]

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
