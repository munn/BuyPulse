"""Pydantic models for scheduler API responses."""

from pydantic import BaseModel


class SchedulerProcessStatus(BaseModel):
    status: str
    uptime_seconds: int
    last_heartbeat: str | None


class SchedulerJobStatus(BaseModel):
    name: str
    status: str
    interval_seconds: int
    last_run_at: str | None
    next_run_at: str | None
    last_result: str | None
    error_count: int


class SchedulerStatusResponse(BaseModel):
    process: SchedulerProcessStatus
    jobs: list[SchedulerJobStatus]
