"""CamelCamelCamel chart image downloader with rate limiting.

Uses curl_cffi to impersonate Chrome's TLS fingerprint (JA3/JA4),
bypassing Cloudflare's TLS-based bot detection. Verified in spike 2026-03-15:
httpx gets blocked after ~15 requests; curl_cffi achieves 20/20 success rate.
"""

from urllib.parse import urlencode

from curl_cffi import CurlError
from curl_cffi.requests import AsyncSession

from cps.crawler.rate_limiter import RateLimiter


class RateLimitError(Exception):
    """Raised when the server responds with HTTP 429 Too Many Requests."""


class BlockedError(Exception):
    """Raised when the server responds with HTTP 403 Forbidden."""


class ServerError(Exception):
    """Raised when the server responds with HTTP 500+."""


class DownloadError(Exception):
    """Raised on connection timeouts and other transport-level failures."""


class CccDownloader:
    """Downloads CCC chart PNG images with built-in rate limiting.

    URL template:
        {base_url}/{asin}/amazon-new-used.png?force=1&zero=0&w=855&h=513&...
    CCC returns 2x resolution (1710x1026) for Retina displays.
    """

    _QUERY_PARAMS = {
        "force": "1",
        "zero": "0",
        "w": "855",
        "h": "513",
        "desired": "false",
        "legend": "1",
        "ilt": "1",
        "tp": "all",
        "fo": "0",
        "lang": "en",
    }

    def __init__(self, base_url: str, rate_limit: float = 1.0) -> None:
        """Initialize the downloader.

        Args:
            base_url: Base URL for the CCC chart service (no trailing slash).
            rate_limit: Maximum requests per second.
        """
        self._base_url = base_url.rstrip("/")
        self._rate_limiter = RateLimiter(rate=rate_limit)

    async def download(self, asin: str) -> bytes:
        """Download a CCC chart image for the given ASIN.

        Args:
            asin: Amazon Standard Identification Number.

        Returns:
            Raw PNG bytes.

        Raises:
            RateLimitError: On HTTP 429.
            BlockedError: On HTTP 403.
            ServerError: On HTTP 500+.
            DownloadError: On connection timeouts or other transport failures.
        """
        await self._rate_limiter.acquire()

        url = f"{self._base_url}/{asin}/amazon-new-used.png?{urlencode(self._QUERY_PARAMS)}"

        try:
            async with AsyncSession(impersonate="chrome") as session:
                response = await session.get(
                    url,
                    timeout=15,
                    allow_redirects=True,
                )
        except CurlError as exc:
            raise DownloadError(str(exc)) from exc

        if response.status_code == 200:
            return response.content

        if response.status_code == 429:
            self._rate_limiter.trigger_cooldown()
            raise RateLimitError(
                f"Rate limited (429) for ASIN {asin}"
            )

        if response.status_code == 403:
            raise BlockedError(
                f"Blocked (403) for ASIN {asin}"
            )

        if response.status_code >= 500:
            raise ServerError(
                f"Server error ({response.status_code}) for ASIN {asin}"
            )

        raise DownloadError(
            f"Unexpected HTTP {response.status_code} for ASIN {asin}"
        )
