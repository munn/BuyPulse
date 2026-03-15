"""CamelCamelCamel chart image downloader with rate limiting."""

import httpx

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
        {base_url}/{asin}/amazon-new-used.png?force=1&zero=0&w=2000&h=800&desired=false&legend=1&ilt=1&tp=all&fo=0
    """

    _QUERY_PARAMS = {
        "force": "1",
        "zero": "0",
        "w": "2000",
        "h": "800",
        "desired": "false",
        "legend": "1",
        "ilt": "1",
        "tp": "all",
        "fo": "0",
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

        url = f"{self._base_url}/{asin}/amazon-new-used.png"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=self._QUERY_PARAMS)
        except httpx.HTTPError as exc:
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
