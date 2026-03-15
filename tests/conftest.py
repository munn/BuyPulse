"""Shared test fixtures for CPS test suite."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def sample_asin() -> str:
    """Return a sample ASIN for testing."""
    return "B08N5WRWNW"


@pytest.fixture
def sample_asins() -> list[str]:
    """Return a list of sample ASINs for batch testing."""
    return [
        "B08N5WRWNW",
        "B09V3KXJPB",
        "B0BSHF7WHW",
        "B0D1XD1ZV3",
        "B0CHX3QBCH",
    ]


@pytest.fixture
def sample_chart_normal() -> Path:
    """Path to a normal CCC chart image with 3 price curves."""
    return FIXTURES_DIR / "sample_chart_normal.png"


@pytest.fixture
def sample_chart_nodata() -> Path:
    """Path to a CCC chart with no data / empty."""
    return FIXTURES_DIR / "sample_chart_nodata.png"


@pytest.fixture
def sample_chart_edge() -> Path:
    """Path to a CCC chart with edge-case prices (very low/high)."""
    return FIXTURES_DIR / "sample_chart_edge.png"
