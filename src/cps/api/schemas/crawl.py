"""Crawler request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class CrawlTaskItem(BaseModel):
    id: int
    product_id: int
    platform_id: str  # joined from product
    platform: str
    status: str
    priority: int
    retry_count: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class CrawlStats(BaseModel):
    pending: int
    running: int
    completed: int
    failed: int
    speed_per_hour: float  # completions/hour in last 24h


class EnqueueRequest(BaseModel):
    platform_ids: list[str] = Field(max_length=500)
    platform: str = "amazon"


class BatchRetryRequest(BaseModel):
    ids: list[int] = Field(max_length=500)
