# tests/unit/test_db_queue.py
"""Tests for DbTaskQueue — PostgreSQL-backed task queue."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from cps.queue.db_queue import DbTaskQueue
from cps.queue.protocol import Task, TaskQueue


class TestDbTaskQueueConformance:
    def test_implements_task_queue_protocol(self):
        mock_session = AsyncMock()
        queue = DbTaskQueue(session=mock_session)
        assert isinstance(queue, TaskQueue)


class TestPopNext:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.flush = AsyncMock()
        session.get = AsyncMock()
        return session

    async def test_returns_none_when_no_pending_tasks(self, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        queue = DbTaskQueue(session=mock_session)
        task = await queue.pop_next("amazon")
        assert task is None

    async def test_returns_task_when_pending_exists(self, mock_session):
        crawl_task = MagicMock()
        crawl_task.id = 42
        crawl_task.product_id = 100
        crawl_task.platform = "amazon"
        crawl_task.status = "pending"
        crawl_task.started_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = crawl_task
        mock_session.execute.return_value = mock_result

        mock_product = MagicMock()
        mock_product.platform_id = "B08N5WRWNW"
        mock_session.get.return_value = mock_product

        queue = DbTaskQueue(session=mock_session)
        task = await queue.pop_next("amazon")

        assert isinstance(task, Task)
        assert task.id == 42
        assert task.product_id == 100
        assert task.platform_id == "B08N5WRWNW"

    async def test_marks_task_in_progress(self, mock_session):
        crawl_task = MagicMock()
        crawl_task.id = 42
        crawl_task.product_id = 100
        crawl_task.platform = "amazon"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = crawl_task
        mock_session.execute.return_value = mock_result

        mock_product = MagicMock()
        mock_product.platform_id = "B08N5WRWNW"
        mock_session.get.return_value = mock_product

        queue = DbTaskQueue(session=mock_session)
        await queue.pop_next("amazon")

        assert crawl_task.status == "in_progress"
        assert crawl_task.started_at is not None

    async def test_returns_none_when_product_not_found(self, mock_session):
        crawl_task = MagicMock()
        crawl_task.id = 42
        crawl_task.product_id = 999

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = crawl_task
        mock_session.execute.return_value = mock_result
        mock_session.get.return_value = None

        queue = DbTaskQueue(session=mock_session)
        task = await queue.pop_next("amazon")
        assert task is None
        assert crawl_task.status == "failed"


class TestComplete:
    async def test_marks_completed_with_next_crawl(self):
        mock_session = AsyncMock()
        crawl_task = MagicMock()
        crawl_task.total_crawls = 5
        mock_session.get.return_value = crawl_task

        queue = DbTaskQueue(session=mock_session)
        await queue.complete(42)

        assert crawl_task.status == "completed"
        assert crawl_task.completed_at is not None
        assert crawl_task.total_crawls == 6
        assert crawl_task.next_crawl_at is not None
        assert crawl_task.error_message is None

    async def test_noop_when_task_not_found(self):
        mock_session = AsyncMock()
        mock_session.get.return_value = None

        queue = DbTaskQueue(session=mock_session)
        await queue.complete(999)  # should not raise


class TestFail:
    async def test_increments_retry_and_requeues_when_under_max(self):
        mock_session = AsyncMock()
        crawl_task = MagicMock()
        crawl_task.retry_count = 1
        crawl_task.max_retries = 3
        mock_session.get.return_value = crawl_task

        queue = DbTaskQueue(session=mock_session)
        await queue.fail(42, "Server error (500)")

        assert crawl_task.retry_count == 2
        assert crawl_task.status == "pending"
        assert crawl_task.error_message == "Server error (500)"

    async def test_marks_failed_when_max_retries_reached(self):
        mock_session = AsyncMock()
        crawl_task = MagicMock()
        crawl_task.retry_count = 2
        crawl_task.max_retries = 3
        mock_session.get.return_value = crawl_task

        queue = DbTaskQueue(session=mock_session)
        await queue.fail(42, "Server error (500)")

        assert crawl_task.retry_count == 3
        assert crawl_task.status == "failed"


class TestRequeue:
    async def test_resets_to_pending_without_retry_increment(self):
        mock_session = AsyncMock()
        crawl_task = MagicMock()
        crawl_task.retry_count = 1
        crawl_task.status = "in_progress"
        mock_session.get.return_value = crawl_task

        queue = DbTaskQueue(session=mock_session)
        await queue.requeue(42)

        assert crawl_task.status == "pending"
        assert crawl_task.started_at is None
        assert crawl_task.error_message is None
        assert crawl_task.retry_count == 1  # not incremented
