# src/cps/queue/protocol.py
"""Task queue protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Task:
    """A unit of work from the queue."""

    id: int
    product_id: int
    platform_id: str
    platform: str


@runtime_checkable
class TaskQueue(Protocol):
    """Abstract task queue for crawl job scheduling."""

    async def pop_next(self, platform: str) -> Task | None: ...
    async def complete(self, task_id: int) -> None: ...
    async def fail(self, task_id: int, error: str) -> None: ...
    async def requeue(self, task_id: int) -> None: ...
