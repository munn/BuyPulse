"""Audit log response schemas."""

from datetime import datetime

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: int
    user_id: int
    action: str
    resource_type: str
    resource_id: str | None
    details: dict | None
    ip_address: str
    created_at: datetime

    model_config = {"from_attributes": True}
