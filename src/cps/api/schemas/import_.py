"""Import job response schemas."""

from datetime import datetime

from pydantic import BaseModel


class ImportJobItem(BaseModel):
    id: int
    filename: str
    status: str
    total: int
    processed: int
    added: int
    skipped: int
    error_message: str | None
    created_by: int
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
