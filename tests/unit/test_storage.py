"""T012: Unit tests for cps.crawler.storage — PngStorage.

These tests verify:
- PNG files are saved to the correct path pattern
- Intermediate directories are created automatically
- Existing files are overwritten without error
- save() returns the absolute path of the saved file
- Invalid platform_id format raises ValueError
"""

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from cps.crawler.storage import PngStorage

FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake png data for testing"


class TestPngStorageSave:
    """PngStorage.save() writes PNG files to a structured directory layout."""

    def test_saves_to_correct_path_pattern(self, tmp_path: Path):
        """File should be saved at {data_dir}/charts/{id[0:2]}/{id}/{date}.png."""
        storage = PngStorage(data_dir=tmp_path)
        platform_id = "B08N5WRWNW"

        today = date.today().isoformat()
        result = storage.save(platform_id=platform_id, png_bytes=FAKE_PNG_BYTES)

        expected = tmp_path / "charts" / "B0" / platform_id / f"{today}.png"
        assert result == expected
        assert result.exists()
        assert result.read_bytes() == FAKE_PNG_BYTES

    def test_platform_id_prefix_two_chars(self, tmp_path: Path):
        """The first subdirectory should be the first 2 characters of the platform_id."""
        storage = PngStorage(data_dir=tmp_path)
        platform_id = "X1YZ345678"

        result = storage.save(platform_id=platform_id, png_bytes=FAKE_PNG_BYTES)

        # First subdir should be "X1"
        assert "X1" in result.parts
        assert result.parent.parent.name == "X1"

    def test_creates_intermediate_directories(self, tmp_path: Path):
        """Directories should be created automatically if they don't exist."""
        storage = PngStorage(data_dir=tmp_path)
        platform_id = "B09V3KXJPB"

        # Ensure target directory doesn't exist yet
        target_dir = tmp_path / "charts" / "B0" / platform_id
        assert not target_dir.exists()

        result = storage.save(platform_id=platform_id, png_bytes=FAKE_PNG_BYTES)

        assert result.exists()
        assert target_dir.exists()


class TestPngStorageOverwrite:
    """Saving the same platform_id on the same day overwrites without error."""

    def test_overwrites_existing_file(self, tmp_path: Path):
        """Second save with same platform_id on same day should overwrite."""
        storage = PngStorage(data_dir=tmp_path)
        platform_id = "B08N5WRWNW"

        first_data = b"first version"
        second_data = b"second version"

        path1 = storage.save(platform_id=platform_id, png_bytes=first_data)
        path2 = storage.save(platform_id=platform_id, png_bytes=second_data)

        assert path1 == path2
        assert path2.read_bytes() == second_data


class TestPngStorageReturnValue:
    """save() returns the absolute path of the saved file."""

    def test_returns_absolute_path(self, tmp_path: Path):
        """Returned path should be absolute."""
        storage = PngStorage(data_dir=tmp_path)
        platform_id = "B0BSHF7WHW"

        result = storage.save(platform_id=platform_id, png_bytes=FAKE_PNG_BYTES)

        assert result.is_absolute()

    def test_returned_path_is_readable(self, tmp_path: Path):
        """The returned path should point to a file we can read back."""
        storage = PngStorage(data_dir=tmp_path)
        platform_id = "B0D1XD1ZV3"

        result = storage.save(platform_id=platform_id, png_bytes=FAKE_PNG_BYTES)

        assert result.read_bytes() == FAKE_PNG_BYTES


class TestPngStorageValidation:
    """Invalid platform_ids should be rejected."""

    def test_rejects_platform_id_too_short(self, tmp_path: Path):
        """platform_id with fewer than 10 characters should raise ValueError."""
        storage = PngStorage(data_dir=tmp_path)

        with pytest.raises(ValueError, match="[Ii]nvalid.*platform_id"):
            storage.save(platform_id="B08N5", png_bytes=FAKE_PNG_BYTES)

    def test_rejects_platform_id_too_long(self, tmp_path: Path):
        """platform_id with more than 10 characters should raise ValueError."""
        storage = PngStorage(data_dir=tmp_path)

        with pytest.raises(ValueError, match="[Ii]nvalid.*platform_id"):
            storage.save(platform_id="B08N5WRWNW1", png_bytes=FAKE_PNG_BYTES)

    def test_rejects_platform_id_with_special_chars(self, tmp_path: Path):
        """platform_id with non-alphanumeric characters should raise ValueError."""
        storage = PngStorage(data_dir=tmp_path)

        with pytest.raises(ValueError, match="[Ii]nvalid.*platform_id"):
            storage.save(platform_id="B08N5-WRWN", png_bytes=FAKE_PNG_BYTES)

    def test_rejects_empty_platform_id(self, tmp_path: Path):
        """Empty string should raise ValueError."""
        storage = PngStorage(data_dir=tmp_path)

        with pytest.raises(ValueError, match="[Ii]nvalid.*platform_id"):
            storage.save(platform_id="", png_bytes=FAKE_PNG_BYTES)

    def test_accepts_valid_10_char_alphanumeric_platform_id(self, tmp_path: Path):
        """Valid 10-character alphanumeric platform_id should not raise."""
        storage = PngStorage(data_dir=tmp_path)

        # Should not raise
        result = storage.save(platform_id="B0CHX3QBCH", png_bytes=FAKE_PNG_BYTES)
        assert result.exists()
