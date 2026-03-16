"""Integration test fixtures — requires running PostgreSQL for DB tests."""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cps.db.models import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://cps_test:cps_test_password@localhost:5433/cps_test",
)

# Year partitions needed for price_history and daily_snapshots
_PARTITION_YEARS = range(2020, 2028)


@pytest.fixture(scope="session")
async def test_engine():
    """Create a test database engine for the entire test session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
async def setup_database(test_engine):
    """Create all tables at session start, drop at session end.

    Gracefully skips if PostgreSQL is not available, allowing non-DB
    integration tests (e.g., downloader with respx) to run.
    """
    try:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Create year partitions with dedup constraints
            # (mirrors Alembic migration 001)
            for year in _PARTITION_YEARS:
                ph = f"price_history_{year}"
                await conn.execute(text(
                    f"CREATE TABLE IF NOT EXISTS {ph} "
                    f"PARTITION OF price_history "
                    f"FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01')"
                ))
                await conn.execute(text(
                    f"ALTER TABLE {ph} ADD CONSTRAINT "
                    f"uq_{ph}_dedup UNIQUE (product_id, price_type, recorded_date)"
                ))
                ds = f"daily_snapshots_{year}"
                await conn.execute(text(
                    f"CREATE TABLE IF NOT EXISTS {ds} "
                    f"PARTITION OF daily_snapshots "
                    f"FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01')"
                ))
    except OSError:
        yield
        return

    yield

    try:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    except OSError:
        pass


@pytest.fixture
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    """Provide a transactional test session that rolls back after each test."""
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()
