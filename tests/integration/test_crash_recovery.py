"""Integration test for crash recovery — quickstart scenario 8 (T035).

Tests that stale in_progress tasks are reset to pending on startup.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import CrawlTask, Product
from cps.pipeline.orchestrator import PipelineOrchestrator


class TestCrashRecovery:
    async def test_resets_stale_in_progress_tasks(self, db_session: AsyncSession):
        """Stale in_progress tasks (started > 1 hour ago) are reset to pending."""
        # Create 3 products with stale in_progress tasks
        stale_time = datetime.now(timezone.utc) - timedelta(hours=2)

        for i in range(3):
            product = Product(platform_id=f"B3TST{i:04d}")
            db_session.add(product)
            await db_session.flush()

            task = CrawlTask(
                product_id=product.id,
                status="in_progress",
                started_at=stale_time,
                retry_count=i,  # different retry counts
            )
            db_session.add(task)
        await db_session.flush()

        # Run crash recovery
        recovered = await PipelineOrchestrator.recover_stale_tasks(db_session)

        assert recovered == 3

        # Verify all tasks reset to pending
        result = await db_session.execute(
            select(CrawlTask).where(CrawlTask.status == "pending")
        )
        tasks = result.scalars().all()
        assert len(tasks) == 3

        # Verify retry_count is preserved
        retry_counts = sorted(t.retry_count for t in tasks)
        assert retry_counts == [0, 1, 2]

    async def test_does_not_reset_recent_in_progress(self, db_session: AsyncSession):
        """Recently started in_progress tasks are NOT reset."""
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=30)

        product = Product(platform_id="B4RCENT000")
        db_session.add(product)
        await db_session.flush()

        task = CrawlTask(
            product_id=product.id,
            status="in_progress",
            started_at=recent_time,
        )
        db_session.add(task)
        await db_session.flush()

        recovered = await PipelineOrchestrator.recover_stale_tasks(db_session)

        assert recovered == 0

        # Task should still be in_progress
        result = await db_session.execute(
            select(CrawlTask).where(CrawlTask.product_id == product.id)
        )
        t = result.scalars().first()
        assert t.status == "in_progress"

    async def test_does_not_affect_other_statuses(self, db_session: AsyncSession):
        """Only in_progress tasks are affected; pending/completed/failed stay unchanged."""
        for i, status in enumerate(["pending", "completed", "failed"]):
            product = Product(platform_id=f"B5STA{i:04d}")
            db_session.add(product)
            await db_session.flush()

            task = CrawlTask(
                product_id=product.id,
                status=status,
            )
            db_session.add(task)
        await db_session.flush()

        recovered = await PipelineOrchestrator.recover_stale_tasks(db_session)

        assert recovered == 0
