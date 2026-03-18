"""Tests for AmazonFetcher — wraps CccDownloader + PngStorage."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.platforms.amazon.fetcher import AmazonFetcher
from cps.platforms.protocol import FetchResult, PlatformFetcher


class TestAmazonFetcherConformance:
    def test_implements_platform_fetcher_protocol(self):
        fetcher = AmazonFetcher(
            base_url="https://charts.example.com",
            data_dir=Path("/tmp"),
        )
        assert isinstance(fetcher, PlatformFetcher)


class TestAmazonFetcherFetch:
    @pytest.fixture
    def fetcher(self, tmp_path):
        return AmazonFetcher(
            base_url="https://charts.example.com",
            data_dir=tmp_path,
            rate_limit=10.0,
        )

    async def test_returns_fetch_result_with_png_bytes(self, fetcher):
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        with (
            patch.object(fetcher._downloader, "download", new_callable=AsyncMock, return_value=png_bytes),
            patch.object(fetcher._storage, "save", return_value=Path("/tmp/chart.png")),
        ):
            result = await fetcher.fetch("B08N5WRWNW")

        assert isinstance(result, FetchResult)
        assert result.raw_data == png_bytes
        assert result.storage_path == "/tmp/chart.png"

    async def test_delegates_to_downloader_with_platform_id(self, fetcher):
        with (
            patch.object(fetcher._downloader, "download", new_callable=AsyncMock, return_value=b"png") as mock_dl,
            patch.object(fetcher._storage, "save", return_value=Path("/tmp/x.png")),
        ):
            await fetcher.fetch("B08N5WRWNW")

        mock_dl.assert_awaited_once_with("B08N5WRWNW")

    async def test_delegates_to_storage_with_bytes(self, fetcher):
        png_bytes = b"fake-png-data"
        with (
            patch.object(fetcher._downloader, "download", new_callable=AsyncMock, return_value=png_bytes),
            patch.object(fetcher._storage, "save", return_value=Path("/tmp/x.png")) as mock_save,
        ):
            await fetcher.fetch("B08N5WRWNW")

        mock_save.assert_called_once_with("B08N5WRWNW", png_bytes)

    async def test_propagates_download_errors(self, fetcher):
        from cps.crawler.downloader import RateLimitError

        with patch.object(fetcher._downloader, "download", new_callable=AsyncMock, side_effect=RateLimitError("429")):
            with pytest.raises(RateLimitError):
                await fetcher.fetch("B08N5WRWNW")
