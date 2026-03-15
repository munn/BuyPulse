"""Integration test fixtures — requires running PostgreSQL for DB tests."""

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cps.db.models import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://cps_test:cps_test_password@localhost:5433/cps_test",
)


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
