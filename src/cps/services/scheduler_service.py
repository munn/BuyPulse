"""Scheduler status service — shared by API and CLI.

Spec Section 8.3 + 8.4.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import SchedulerJob


def _derive_process_status(
    job_status: str,
    started_at: datetime | None,
    last_heartbeat: datetime | None,
    now: datetime,
    interval_s: int,
) -> str:
    """Derive process liveness from scheduler_jobs row.

    - started_at set + fresh heartbeat (< 2x interval) -> "running"
    - status == "offline" or no heartbeat/started_at -> "offline"
    - Stale heartbeat (>= 2x interval) -> "dead"
    """
    if job_status == "offline":
        return "offline"
    if started_at is None or last_heartbeat is None:
        return "offline"
    elapsed = (now - last_heartbeat).total_seconds()
    if elapsed >= 2 * interval_s:
        return "dead"
    return "running"


async def get_scheduler_status(session: AsyncSession) -> dict:
    """Build the full scheduler status response.

    Used by both GET /scheduler/status API and `cps scheduler status` CLI.
    """
    now = datetime.now(timezone.utc)
    result = await session.execute(select(SchedulerJob))
    jobs = list(result.scalars().all())

    process_status = "offline"
    uptime_seconds = 0
    last_heartbeat_iso = None

    if jobs:
        first = jobs[0]
        process_status = _derive_process_status(
            first.status, first.started_at, first.last_heartbeat, now, first.interval_s
        )
        if first.started_at:
            uptime_seconds = int((now - first.started_at).total_seconds())
        if first.last_heartbeat:
            last_heartbeat_iso = first.last_heartbeat.isoformat()

    job_list = [
        {
            "name": j.name,
            "status": j.status,
            "interval_seconds": j.interval_s,
            "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
            "next_run_at": j.next_run_at.isoformat() if j.next_run_at else None,
            "last_result": j.last_result,
            "error_count": j.error_count,
        }
        for j in jobs
    ]

    return {
        "process": {
            "status": process_status,
            "uptime_seconds": uptime_seconds,
            "last_heartbeat": last_heartbeat_iso,
        },
        "jobs": job_list,
    }
