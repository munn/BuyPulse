"""Dashboard response schemas."""

from datetime import datetime

from pydantic import BaseModel


class OverviewStats(BaseModel):
    products_total: int
    products_today: int
    crawled_total: int
    crawled_today: int
    success_rate_24h: float
    price_records_total: int


class ThroughputBucket(BaseModel):
    hour: datetime
    count: int


class WorkerStatus(BaseModel):
    worker_id: str
    platform: str
    status: str  # online/idle/offline
    current_task_id: int | None
    tasks_completed: int
    last_heartbeat: datetime
    started_at: datetime


class RecentFailure(BaseModel):
    task_id: int
    platform_id: str
    platform: str
    error_message: str | None
    updated_at: datetime
