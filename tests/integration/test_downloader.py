"""Integration tests for CCC chart downloader.

Tests HTTP response handling by mocking curl_cffi's AsyncSession.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from curl_cffi import CurlError

from cps.crawler.downloader import (
    BlockedError,
    CccDownloader,
    DownloadError,
    RateLimitError,
    ServerError,
)

CCC_BASE_URL = "https://charts.camelcamelcamel.com/us"
SAMPLE_PLATFORM_ID = "B08N5WRWNW"


@pytest.fixture
def downloader():
    """Create a downloader instance with fast rate limiter."""
    return CccDownloader(base_url=CCC_BASE_URL, rate_limit=100.0)


@pytest.fixture
def png_bytes() -> bytes:
    """Minimal valid PNG file header."""
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"
        b"\x00\x00\x00\x90wS\xde"
    )


def _mock_response(status_code: int, content: bytes = b"") -> MagicMock:
    """Create a mock curl_cffi response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    return resp


class TestSuccessfulDownload:
    async def test_returns_png_bytes_on_success(self, downloader, png_bytes):
        """Successful download returns raw PNG bytes."""
        mock_resp = _mock_response(200, png_bytes)

        with patch("cps.crawler.downloader.AsyncSession") as MockSession:
            session_instance = AsyncMock()
            session_instance.get = AsyncMock(return_value=mock_resp)
            MockSession.return_value.__aenter__ = AsyncMock(return_value=session_instance)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await downloader.download(SAMPLE_PLATFORM_ID)

        assert result == png_bytes

    async def test_correct_url_contains_platform_id_and_params(self, downloader, png_bytes):
        """URL includes platform_id and correct query parameters."""
        mock_resp = _mock_response(200, png_bytes)

        with patch("cps.crawler.downloader.AsyncSession") as MockSession:
            session_instance = AsyncMock()
            session_instance.get = AsyncMock(return_value=mock_resp)
            MockSession.return_value.__aenter__ = AsyncMock(return_value=session_instance)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            await downloader.download(SAMPLE_PLATFORM_ID)

            call_args = session_instance.get.call_args
            url = call_args[0][0]
            assert SAMPLE_PLATFORM_ID in url
            assert "force=1" in url
            assert "w=855" in url
            assert "h=513" in url

    async def test_uses_chrome_impersonation(self, downloader, png_bytes):
        """Session is created with Chrome TLS impersonation."""
        mock_resp = _mock_response(200, png_bytes)

        with patch("cps.crawler.downloader.AsyncSession") as MockSession:
            session_instance = AsyncMock()
            session_instance.get = AsyncMock(return_value=mock_resp)
            MockSession.return_value.__aenter__ = AsyncMock(return_value=session_instance)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            await downloader.download(SAMPLE_PLATFORM_ID)

            MockSession.assert_called_once_with(impersonate="chrome")


class TestErrorHandling:
    async def test_http_429_raises_rate_limit_error(self, downloader):
        """HTTP 429 Too Many Requests raises RateLimitError."""
        mock_resp = _mock_response(429)

        with patch("cps.crawler.downloader.AsyncSession") as MockSession:
            session_instance = AsyncMock()
            session_instance.get = AsyncMock(return_value=mock_resp)
            MockSession.return_value.__aenter__ = AsyncMock(return_value=session_instance)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(RateLimitError):
                await downloader.download(SAMPLE_PLATFORM_ID)

    async def test_http_403_raises_blocked_error(self, downloader):
        """HTTP 403 Forbidden raises BlockedError."""
        mock_resp = _mock_response(403)

        with patch("cps.crawler.downloader.AsyncSession") as MockSession:
            session_instance = AsyncMock()
            session_instance.get = AsyncMock(return_value=mock_resp)
            MockSession.return_value.__aenter__ = AsyncMock(return_value=session_instance)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(BlockedError):
                await downloader.download(SAMPLE_PLATFORM_ID)

    async def test_http_500_raises_server_error(self, downloader):
        """HTTP 500 Internal Server Error raises ServerError."""
        mock_resp = _mock_response(500)

        with patch("cps.crawler.downloader.AsyncSession") as MockSession:
            session_instance = AsyncMock()
            session_instance.get = AsyncMock(return_value=mock_resp)
            MockSession.return_value.__aenter__ = AsyncMock(return_value=session_instance)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ServerError):
                await downloader.download(SAMPLE_PLATFORM_ID)

    async def test_curl_error_raises_download_error(self, downloader):
        """CurlError raises DownloadError."""
        with patch("cps.crawler.downloader.AsyncSession") as MockSession:
            session_instance = AsyncMock()
            session_instance.get = AsyncMock(side_effect=CurlError("timed out"))
            MockSession.return_value.__aenter__ = AsyncMock(return_value=session_instance)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(DownloadError):
                await downloader.download(SAMPLE_PLATFORM_ID)
