"""Integration tests for scheduler tick — requires PostgreSQL."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import CrawlTask, Product, SchedulerJob


@pytest.fixture
async def scheduler_job_row(db_session: AsyncSession):
    """Ensure a scheduler_jobs row exists for tests."""
    job = SchedulerJob(name="crawl_scheduler", status="idle", interval_s=300)
    db_session.add(job)
    await db_session.flush()
    return job


@pytest.fixture
async def product_with_task(db_session: AsyncSession):
    """Create a product + crawl_task pair."""
    product = Product(platform_id="B08TEST001", platform="amazon")
    db_session.add(product)
    await db_session.flush()
    task = CrawlTask(
        product_id=product.id,
        platform="amazon",
        priority=5,
        status="completed",
        next_crawl_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(task)
    await db_session.flush()
    return product, task


class TestCrawlSchedulerTick:
    """Spec Section 3.1 — tick rescheduling logic."""

    @pytest.mark.anyio
    async def test_reschedules_due_completed_task(self, db_session, scheduler_job_row, product_with_task):
        from cps.scheduler.crawl_job import crawl_scheduler_tick

        _, task = product_with_task
        result = await crawl_scheduler_tick(db_session)

        assert result.rescheduled == 1
        assert task.status == "pending"
        assert task.retry_count == 0
        assert task.error_message is None

    @pytest.mark.anyio
    async def test_skips_task_not_yet_due(self, db_session, scheduler_job_row):
        from cps.scheduler.crawl_job import crawl_scheduler_tick

        product = Product(platform_id="B08FUTURE1", platform="amazon")
        db_session.add(product)
        await db_session.flush()
        task = CrawlTask(
            product_id=product.id, platform="amazon", priority=5,
            status="completed",
            next_crawl_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db_session.add(task)
        await db_session.flush()

        result = await crawl_scheduler_tick(db_session)
        assert result.rescheduled == 0
        assert task.status == "completed"

    @pytest.mark.anyio
    async def test_skips_in_progress_task(self, db_session, scheduler_job_row):
        from cps.scheduler.crawl_job import crawl_scheduler_tick

        product = Product(platform_id="B08INPROG1", platform="amazon")
        db_session.add(product)
        await db_session.flush()
        task = CrawlTask(
            product_id=product.id, platform="amazon", priority=5,
            status="in_progress",
            next_crawl_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(task)
        await db_session.flush()

        result = await crawl_scheduler_tick(db_session)
        assert result.rescheduled == 0
        assert task.status == "in_progress"

    @pytest.mark.anyio
    async def test_skips_failed_task(self, db_session, scheduler_job_row):
        from cps.scheduler.crawl_job import crawl_scheduler_tick

        product = Product(platform_id="B08FAILED1", platform="amazon")
        db_session.add(product)
        await db_session.flush()
        task = CrawlTask(
            product_id=product.id, platform="amazon", priority=5,
            status="failed",
            next_crawl_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(task)
        await db_session.flush()

        result = await crawl_scheduler_tick(db_session)
        assert result.rescheduled == 0
        assert task.status == "failed"

    @pytest.mark.anyio
    async def test_skips_null_next_crawl_at(self, db_session, scheduler_job_row):
        from cps.scheduler.crawl_job import crawl_scheduler_tick

        product = Product(platform_id="B08NONULL1", platform="amazon")
        db_session.add(product)
        await db_session.flush()
        task = CrawlTask(
            product_id=product.id, platform="amazon", priority=5,
            status="completed", next_crawl_at=None,
        )
        db_session.add(task)
        await db_session.flush()

        result = await crawl_scheduler_tick(db_session)
        assert result.rescheduled == 0
        assert task.status == "completed"

    @pytest.mark.anyio
    async def test_idempotent_two_ticks(self, db_session, scheduler_job_row, product_with_task):
        from cps.scheduler.crawl_job import crawl_scheduler_tick

        result1 = await crawl_scheduler_tick(db_session)
        assert result1.rescheduled == 1

        result2 = await crawl_scheduler_tick(db_session)
        assert result2.rescheduled == 0
