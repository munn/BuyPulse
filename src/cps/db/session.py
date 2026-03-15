"""Async SQLAlchemy session factory."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str):
    """Create an async SQLAlchemy engine."""
    return create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
    )


def create_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the given database URL."""
    engine = create_engine(database_url)
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield an async session and ensure it is closed after use."""
    async with session_factory() as session:
        yield session
