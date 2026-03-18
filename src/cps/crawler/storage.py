"""PNG chart storage with structured directory layout."""

import re
from datetime import date
from pathlib import Path


class PngStorage:
    """Saves PNG chart images to a structured directory hierarchy.

    Directory layout: {data_dir}/charts/{platform_id[0:2]}/{platform_id}/{YYYY-MM-DD}.png
    """

    _AMAZON_ASIN_PATTERN = re.compile(r"^[A-Za-z0-9]{10}$")

    def __init__(self, data_dir: Path) -> None:
        """Initialize storage with the root data directory.

        Args:
            data_dir: Root directory for all chart storage.
        """
        self._data_dir = data_dir

    def save(self, platform_id: str, png_bytes: bytes) -> Path:
        """Save a PNG chart image for the given platform_id.

        Args:
            platform_id: Product identifier (e.g. Amazon ASIN, 10 alphanumeric chars).
            png_bytes: Raw PNG image data.

        Returns:
            Absolute path to the saved file.

        Raises:
            ValueError: If platform_id is not exactly 10 alphanumeric characters.
        """
        if not self._AMAZON_ASIN_PATTERN.match(platform_id):
            raise ValueError(
                f"Invalid platform_id: '{platform_id}' — must be exactly 10 alphanumeric characters"
            )

        prefix = platform_id[:2]
        today = date.today().isoformat()

        target_dir = self._data_dir / "charts" / prefix / platform_id
        target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / f"{today}.png"
        file_path.write_bytes(png_bytes)

        return file_path.resolve()
