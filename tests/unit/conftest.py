"""Unit test conftest — override session-scoped DB fixtures for unit tests.

Unit tests do not require a database connection. This conftest overrides
the autouse setup_database fixture from the root conftest to make it a no-op.
"""

import pytest


@pytest.fixture(scope="session")
async def test_engine():
    """No-op engine for unit tests — no database needed."""
    yield None


@pytest.fixture(scope="session", autouse=True)
async def setup_database(test_engine):
    """No-op database setup for unit tests."""
    yield
