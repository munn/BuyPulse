"""Integration tests for CCC chart downloader (T019).

Tests HTTP interactions using respx mock. All tests should FAIL until
the downloader module is implemented in Phase 3.
"""

import httpx
import pytest
import respx

from cps.crawler.downloader import (
    BlockedError,
    CccDownloader,
    DownloadError,
    RateLimitError,
    ServerError,
)

CCC_BASE_URL = "https://charts.camelcamelcamel.com/us"
SAMPLE_ASIN = "B08N5WRWNW"


@pytest.fixture
def downloader():
    """Create a downloader instance with mocked rate limiter."""
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


class TestSuccessfulDownload:
    @respx.mock
    async def test_returns_png_bytes_on_success(self, downloader, png_bytes):
        """Successful download returns raw PNG bytes."""
        url_pattern = f"{CCC_BASE_URL}/{SAMPLE_ASIN}/amazon-new-used.png"
        respx.get(url_pattern).mock(
            return_value=httpx.Response(200, content=png_bytes)
        )
        result = await downloader.download(SAMPLE_ASIN)
        assert result == png_bytes

    @respx.mock
    async def test_correct_url_template(self, downloader, png_bytes):
        """URL includes ASIN and correct query parameters."""
        route = respx.get(
            f"{CCC_BASE_URL}/{SAMPLE_ASIN}/amazon-new-used.png"
        ).mock(return_value=httpx.Response(200, content=png_bytes))

        await downloader.download(SAMPLE_ASIN)

        assert route.called
        request = route.calls[0].request
        assert SAMPLE_ASIN in str(request.url)
        assert "force=1" in str(request.url)
        assert "w=855" in str(request.url)
        assert "h=513" in str(request.url)

    @respx.mock
    async def test_uses_real_ua_string(self, downloader, png_bytes):
        """Request includes a real httpx User-Agent, not python-requests."""
        route = respx.get(
            f"{CCC_BASE_URL}/{SAMPLE_ASIN}/amazon-new-used.png"
        ).mock(return_value=httpx.Response(200, content=png_bytes))

        await downloader.download(SAMPLE_ASIN)

        request = route.calls[0].request
        ua = request.headers.get("user-agent", "")
        assert "python-requests" not in ua
        assert "Go-http-client" not in ua


class TestErrorHandling:
    @respx.mock
    async def test_http_429_raises_rate_limit_error(self, downloader):
        """HTTP 429 Too Many Requests raises RateLimitError."""
        respx.get(
            f"{CCC_BASE_URL}/{SAMPLE_ASIN}/amazon-new-used.png"
        ).mock(return_value=httpx.Response(429))

        with pytest.raises(RateLimitError):
            await downloader.download(SAMPLE_ASIN)

    @respx.mock
    async def test_http_403_raises_blocked_error(self, downloader):
        """HTTP 403 Forbidden raises BlockedError."""
        respx.get(
            f"{CCC_BASE_URL}/{SAMPLE_ASIN}/amazon-new-used.png"
        ).mock(return_value=httpx.Response(403))

        with pytest.raises(BlockedError):
            await downloader.download(SAMPLE_ASIN)

    @respx.mock
    async def test_http_500_raises_server_error(self, downloader):
        """HTTP 500 Internal Server Error raises ServerError."""
        respx.get(
            f"{CCC_BASE_URL}/{SAMPLE_ASIN}/amazon-new-used.png"
        ).mock(return_value=httpx.Response(500))

        with pytest.raises(ServerError):
            await downloader.download(SAMPLE_ASIN)

    @respx.mock
    async def test_timeout_raises_download_error(self, downloader):
        """Connection timeout raises DownloadError."""
        respx.get(
            f"{CCC_BASE_URL}/{SAMPLE_ASIN}/amazon-new-used.png"
        ).mock(side_effect=httpx.ConnectTimeout("timed out"))

        with pytest.raises(DownloadError):
            await downloader.download(SAMPLE_ASIN)
