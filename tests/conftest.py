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
    """Path to a real CCC chart image with 3 price curves (iPad Air)."""
    return FIXTURES_DIR / "real_chart_ipad.png"


@pytest.fixture
def sample_chart_nodata() -> Path:
    """Path to a real CCC 'no data' placeholder image."""
    return FIXTURES_DIR / "real_chart_nodata.png"


@pytest.fixture
def sample_chart_edge() -> Path:
    """Path to a real CCC chart with low prices ($5-$55 range)."""
    return FIXTURES_DIR / "real_chart_case.png"
