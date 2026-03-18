# tests/unit/test_worker.py
"""Tests for the generic worker loop."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.queue.protocol import Task
from cps.worker import WorkerLoop


class TestWorkerLoop:
    @pytest.fixture
    def mock_queue(self):
        queue = AsyncMock()
        queue.pop_next = AsyncMock(return_value=None)
        queue.complete = AsyncMock()
        queue.fail = AsyncMock()
        queue.requeue = AsyncMock()
        return queue

    @pytest.fixture
    def mock_fetcher(self):
        return AsyncMock()

    @pytest.fixture
    def mock_parser(self):
        return MagicMock()

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    def test_creates_worker_loop(self, mock_session, mock_queue, mock_fetcher, mock_parser):
        worker = WorkerLoop(
            session=mock_session,
            queue=mock_queue,
            fetcher=mock_fetcher,
            parser=mock_parser,
            platform="amazon",
        )
        assert worker is not None

    async def test_returns_false_when_no_tasks(self, mock_session, mock_queue, mock_fetcher, mock_parser):
        mock_queue.pop_next.return_value = None

        worker = WorkerLoop(
            session=mock_session,
            queue=mock_queue,
            fetcher=mock_fetcher,
            parser=mock_parser,
            platform="amazon",
        )

        result = await worker.run_once()
        assert result is False

    async def test_processes_task_successfully(self, mock_session, mock_queue, mock_fetcher, mock_parser):
        task = Task(id=1, product_id=42, platform_id="B08N5WRWNW", platform="amazon")
        mock_queue.pop_next.return_value = task

        from cps.platforms.protocol import FetchResult, ParseResult

        mock_fetcher.fetch.return_value = FetchResult(raw_data=b"png", storage_path="/tmp/x.png")
        mock_parser.parse.return_value = ParseResult(records=[], points_extracted=0)

        worker = WorkerLoop(
            session=mock_session,
            queue=mock_queue,
            fetcher=mock_fetcher,
            parser=mock_parser,
            platform="amazon",
        )

        with patch("cps.worker.store_results", new_callable=AsyncMock, return_value=1):
            result = await worker.run_once()

        assert result is True
        mock_queue.complete.assert_awaited_once_with(1)

    async def test_handles_download_error(self, mock_session, mock_queue, mock_fetcher, mock_parser):
        from cps.crawler.downloader import DownloadError

        task = Task(id=1, product_id=42, platform_id="B08N5WRWNW", platform="amazon")
        mock_queue.pop_next.return_value = task
        mock_fetcher.fetch.side_effect = DownloadError("timeout")

        worker = WorkerLoop(
            session=mock_session,
            queue=mock_queue,
            fetcher=mock_fetcher,
            parser=mock_parser,
            platform="amazon",
        )

        result = await worker.run_once()
        assert result is False
        mock_queue.fail.assert_awaited_once_with(1, "timeout")

    async def test_handles_rate_limit(self, mock_session, mock_queue, mock_fetcher, mock_parser):
        from cps.crawler.downloader import RateLimitError

        task = Task(id=1, product_id=42, platform_id="B08N5WRWNW", platform="amazon")
        mock_queue.pop_next.return_value = task
        mock_fetcher.fetch.side_effect = RateLimitError("429")

        worker = WorkerLoop(
            session=mock_session,
            queue=mock_queue,
            fetcher=mock_fetcher,
            parser=mock_parser,
            platform="amazon",
        )

        result = await worker.run_once()
        assert result is False
        mock_queue.requeue.assert_awaited_once_with(1)
