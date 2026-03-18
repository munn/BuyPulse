"""Amazon platform fetcher — downloads CCC chart images."""

from pathlib import Path

from cps.crawler.downloader import CccDownloader
from cps.crawler.storage import PngStorage
from cps.platforms.protocol import FetchResult


class AmazonFetcher:
    """Fetches CCC chart PNG images for Amazon products.

    Wraps the existing CccDownloader (curl_cffi) and PngStorage.
    """

    def __init__(self, base_url: str, data_dir: Path, rate_limit: float = 1.0) -> None:
        self._downloader = CccDownloader(base_url=base_url, rate_limit=rate_limit)
        self._storage = PngStorage(data_dir=data_dir)

    async def fetch(self, platform_id: str) -> FetchResult:
        """Download a CCC chart PNG and save it to disk.

        Raises:
            RateLimitError: On HTTP 429.
            BlockedError: On HTTP 403.
            ServerError: On HTTP 500+.
            DownloadError: On connection failures.
        """
        png_bytes = await self._downloader.download(platform_id)
        chart_path = self._storage.save(platform_id, png_bytes)
        return FetchResult(raw_data=png_bytes, storage_path=str(chart_path))
