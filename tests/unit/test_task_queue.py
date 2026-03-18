# tests/unit/test_task_queue.py
"""Tests for task queue types and protocol."""

import pytest

from cps.queue.protocol import Task, TaskQueue


class TestTask:
    def test_frozen_dataclass(self):
        task = Task(id=1, product_id=42, platform_id="B08N5WRWNW", platform="amazon")
        assert task.id == 1
        assert task.platform_id == "B08N5WRWNW"
        assert task.platform == "amazon"

    def test_immutable(self):
        task = Task(id=1, product_id=42, platform_id="B08N5WRWNW", platform="amazon")
        with pytest.raises(AttributeError):
            task.id = 2


class TestTaskQueueProtocol:
    def test_conforming_class_passes_check(self):
        class FakeQueue:
            async def pop_next(self, platform: str) -> Task | None:
                return None
            async def complete(self, task_id: int) -> None:
                pass
            async def fail(self, task_id: int, error: str) -> None:
                pass
            async def requeue(self, task_id: int) -> None:
                pass

        assert isinstance(FakeQueue(), TaskQueue)

    def test_non_conforming_class_fails_check(self):
        class NotAQueue:
            async def pop(self):
                pass

        assert not isinstance(NotAQueue(), TaskQueue)
