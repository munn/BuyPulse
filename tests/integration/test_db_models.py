"""Integration tests for DB models with test PostgreSQL (T020).

These tests require a running test PostgreSQL instance (docker-compose db-test).
All tests should FAIL until implementation is complete and DB is available.
"""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import (
    CrawlTask,
    ExtractionRun,
    PriceHistory,
    PriceSummary,
    Product,
)


class TestProductModel:
    async def test_create_product(self, db_session: AsyncSession):
        """Can create a product with a valid ASIN."""
        product = Product(asin="B08N5WRWNW")
        db_session.add(product)
        await db_session.flush()

        assert product.id is not None
        assert product.asin == "B08N5WRWNW"
        assert product.first_seen is not None

    async def test_asin_uniqueness(self, db_session: AsyncSession):
        """Duplicate ASIN raises IntegrityError."""
        p1 = Product(asin="B08N5WRWNW")
        p2 = Product(asin="B08N5WRWNW")
        db_session.add(p1)
        await db_session.flush()

        db_session.add(p2)
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestExtractionRunModel:
    async def test_create_extraction_run(self, db_session: AsyncSession):
        """Can create an extraction run linked to a product."""
        product = Product(asin="B09V3KXJPB")
        db_session.add(product)
        await db_session.flush()

        run = ExtractionRun(
            product_id=product.id,
            chart_path="data/charts/B0/B09V3KXJPB/2026-03-14.png",
            status="success",
            points_extracted=42,
            ocr_confidence=0.95,
            validation_passed=True,
        )
        db_session.add(run)
        await db_session.flush()

        assert run.id is not None
        assert run.product_id == product.id


class TestPriceHistoryModel:
    async def test_insert_price_history(self, db_session: AsyncSession):
        """Can insert rows into price_history (partition routing)."""
        product = Product(asin="B0BSHF7WHW")
        db_session.add(product)
        await db_session.flush()

        ph = PriceHistory(
            product_id=product.id,
            price_type="amazon",
            recorded_date=date(2024, 6, 15),
            price_cents=2999,
        )
        db_session.add(ph)
        await db_session.flush()

        assert ph.id is not None

    async def test_upsert_no_duplicates(self, db_session: AsyncSession):
        """Inserting duplicate (product_id, price_type, recorded_date) is rejected."""
        product = Product(asin="B0D1XD1ZV3")
        db_session.add(product)
        await db_session.flush()

        ph1 = PriceHistory(
            product_id=product.id,
            price_type="amazon",
            recorded_date=date(2024, 6, 15),
            price_cents=2999,
        )
        db_session.add(ph1)
        await db_session.flush()

        ph2 = PriceHistory(
            product_id=product.id,
            price_type="amazon",
            recorded_date=date(2024, 6, 15),
            price_cents=3199,
        )
        db_session.add(ph2)
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestPriceSummaryModel:
    async def test_upsert_price_summary(self, db_session: AsyncSession):
        """PriceSummary enforces unique (product_id, price_type)."""
        product = Product(asin="B0CHX3QBCH")
        db_session.add(product)
        await db_session.flush()

        ps = PriceSummary(
            product_id=product.id,
            price_type="amazon",
            lowest_price=1500,
            lowest_date=date(2024, 8, 1),
            highest_price=7000,
            highest_date=date(2024, 3, 1),
            current_price=5000,
            current_date=date(2025, 1, 1),
        )
        db_session.add(ps)
        await db_session.flush()

        # Duplicate should fail
        ps2 = PriceSummary(
            product_id=product.id,
            price_type="amazon",
            current_price=5500,
        )
        db_session.add(ps2)
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestCrawlTaskModel:
    async def test_create_crawl_task(self, db_session: AsyncSession):
        """Can create a crawl task linked to a product."""
        product = Product(asin="B07XJ8C8F5")
        db_session.add(product)
        await db_session.flush()

        task = CrawlTask(
            product_id=product.id,
            priority=5,
            status="pending",
        )
        db_session.add(task)
        await db_session.flush()

        assert task.id is not None
        assert task.status == "pending"

    async def test_product_uniqueness(self, db_session: AsyncSession):
        """Only one crawl_task per product."""
        product = Product(asin="B08HR46ZSQ")
        db_session.add(product)
        await db_session.flush()

        t1 = CrawlTask(product_id=product.id)
        db_session.add(t1)
        await db_session.flush()

        t2 = CrawlTask(product_id=product.id)
        db_session.add(t2)
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_stale_task_reset_query(self, db_session: AsyncSession):
        """Can query and reset stale in_progress tasks."""
        product = Product(asin="B09G9FPHY6")
        db_session.add(product)
        await db_session.flush()

        stale_time = datetime(2026, 3, 14, 10, 0, 0, tzinfo=timezone.utc)
        task = CrawlTask(
            product_id=product.id,
            status="in_progress",
            started_at=stale_time,
        )
        db_session.add(task)
        await db_session.flush()

        # Query stale tasks (started > 1 hour ago)
        cutoff = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc)
        result = await db_session.execute(
            select(CrawlTask).where(
                CrawlTask.status == "in_progress",
                CrawlTask.started_at < cutoff,
            )
        )
        stale_tasks = result.scalars().all()
        assert len(stale_tasks) == 1
        assert stale_tasks[0].product_id == product.id
