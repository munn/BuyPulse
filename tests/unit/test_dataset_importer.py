"""Tests for UCSD Amazon dataset ASIN extraction."""

import gzip
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.seeds.dataset_importer import (
    extract_asins_from_directory,
    extract_asins_from_metadata,
    submit_asins_in_batches,
)


class TestExtractAsinsFromMetadata:
    def _write_jsonl_gz(self, path: Path, records: list[dict]) -> Path:
        """Helper: write records as gzip-compressed JSONL."""
        file_path = path / "test_meta.jsonl.gz"
        with gzip.open(file_path, "wt", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        return file_path

    def test_extracts_parent_asin(self, tmp_path):
        records = [
            {"parent_asin": "B08N5WRWNW", "title": "Product A"},
            {"parent_asin": "B09V3KXJPB", "title": "Product B"},
        ]
        path = self._write_jsonl_gz(tmp_path, records)
        asins = list(extract_asins_from_metadata(path))
        assert asins == ["B08N5WRWNW", "B09V3KXJPB"]

    def test_deduplicates_asins(self, tmp_path):
        records = [
            {"parent_asin": "B08N5WRWNW", "title": "A"},
            {"parent_asin": "B08N5WRWNW", "title": "A variant"},
            {"parent_asin": "B09V3KXJPB", "title": "B"},
        ]
        path = self._write_jsonl_gz(tmp_path, records)
        asins = list(extract_asins_from_metadata(path))
        assert asins == ["B08N5WRWNW", "B09V3KXJPB"]

    def test_skips_records_without_parent_asin(self, tmp_path):
        records = [
            {"parent_asin": "B08N5WRWNW", "title": "A"},
            {"title": "No ASIN"},
            {"parent_asin": "", "title": "Empty ASIN"},
        ]
        path = self._write_jsonl_gz(tmp_path, records)
        asins = list(extract_asins_from_metadata(path))
        assert asins == ["B08N5WRWNW"]

    def test_skips_malformed_json_lines(self, tmp_path):
        file_path = tmp_path / "bad.jsonl.gz"
        with gzip.open(file_path, "wt", encoding="utf-8") as f:
            f.write('{"parent_asin": "B08N5WRWNW"}\n')
            f.write("not valid json\n")
            f.write('{"parent_asin": "B09V3KXJPB"}\n')
        asins = list(extract_asins_from_metadata(file_path))
        assert asins == ["B08N5WRWNW", "B09V3KXJPB"]

    def test_filters_invalid_asin_format(self, tmp_path):
        records = [
            {"parent_asin": "B08N5WRWNW", "title": "Valid 10-char"},
            {"parent_asin": "SHORT", "title": "Too short"},
            {"parent_asin": "B08N5WRWNW!", "title": "Special char"},
        ]
        path = self._write_jsonl_gz(tmp_path, records)
        asins = list(extract_asins_from_metadata(path))
        assert asins == ["B08N5WRWNW"]

    def test_empty_file_returns_empty(self, tmp_path):
        path = self._write_jsonl_gz(tmp_path, [])
        asins = list(extract_asins_from_metadata(path))
        assert asins == []


class TestSubmitAsinsInBatches:
    @pytest.fixture
    def mock_pipeline(self):
        from unittest.mock import AsyncMock

        from cps.discovery.pipeline import SubmitResult

        pipeline = AsyncMock()
        pipeline.submit_candidates = AsyncMock(
            side_effect=[
                SubmitResult(submitted=100, skipped=0, total=100),
                SubmitResult(submitted=100, skipped=0, total=100),
                SubmitResult(submitted=50, skipped=0, total=50),
            ]
        )
        return pipeline

    @pytest.mark.asyncio
    async def test_submits_in_batches(self, mock_pipeline):
        asins = [f"B{str(i).zfill(9)}" for i in range(250)]
        result = await submit_asins_in_batches(mock_pipeline, iter(asins), batch_size=100)

        assert mock_pipeline.submit_candidates.call_count == 3
        assert result.submitted == 250  # 100 + 100 + 50
        assert result.total == 250  # ASINs consumed from iterator

    @pytest.mark.asyncio
    async def test_respects_max_candidates(self, mock_pipeline):
        from unittest.mock import AsyncMock

        from cps.discovery.pipeline import SubmitResult

        mock_pipeline.submit_candidates = AsyncMock(
            side_effect=[
                SubmitResult(submitted=100, skipped=0, total=100),
                SubmitResult(submitted=100, skipped=0, total=100),
            ]
        )
        asins = [f"B{str(i).zfill(9)}" for i in range(500)]
        result = await submit_asins_in_batches(
            mock_pipeline, iter(asins), batch_size=100, max_candidates=200
        )

        assert mock_pipeline.submit_candidates.call_count == 2
        assert result.total == 200

    @pytest.mark.asyncio
    async def test_empty_iterator(self, mock_pipeline):
        from unittest.mock import AsyncMock

        mock_pipeline.submit_candidates = AsyncMock()
        result = await submit_asins_in_batches(mock_pipeline, iter([]))
        assert result.submitted == 0
        assert result.total == 0
        assert mock_pipeline.submit_candidates.call_count == 0

    @pytest.mark.asyncio
    async def test_accumulates_skipped(self, mock_pipeline):
        from unittest.mock import AsyncMock

        from cps.discovery.pipeline import SubmitResult

        mock_pipeline.submit_candidates = AsyncMock(
            return_value=SubmitResult(submitted=80, skipped=20, total=100)
        )
        asins = [f"B{str(i).zfill(9)}" for i in range(100)]
        result = await submit_asins_in_batches(mock_pipeline, iter(asins), batch_size=100)
        assert result.submitted == 80
        assert result.skipped == 20


class TestExtractAsinsFromDirectory:
    def _write_jsonl_gz(self, path: Path, filename: str, records: list[dict]) -> Path:
        file_path = path / filename
        with gzip.open(file_path, "wt", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        return file_path

    def test_merges_asins_from_multiple_files(self, tmp_path):
        self._write_jsonl_gz(tmp_path, "meta_Electronics.jsonl.gz", [
            {"parent_asin": "B08N5WRWNW"},
            {"parent_asin": "B09V3KXJPB"},
        ])
        self._write_jsonl_gz(tmp_path, "meta_Toys.jsonl.gz", [
            {"parent_asin": "B09V3KXJPB"},  # duplicate across files
            {"parent_asin": "B07XJ8C8F5"},
        ])
        asins = list(extract_asins_from_directory(tmp_path))
        assert len(asins) == 3  # deduplicated across files

    def test_skips_non_jsonl_gz_files(self, tmp_path):
        self._write_jsonl_gz(tmp_path, "meta_Electronics.jsonl.gz", [
            {"parent_asin": "B08N5WRWNW"},
        ])
        (tmp_path / "readme.txt").write_text("not a dataset")
        asins = list(extract_asins_from_directory(tmp_path))
        assert asins == ["B08N5WRWNW"]

    def test_empty_directory(self, tmp_path):
        asins = list(extract_asins_from_directory(tmp_path))
        assert asins == []


class TestDatasetImportIntegration:
    """Integration-style test using mock DB session."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        # Return empty set for existing check (all ASINs are new)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)
        return session

    @pytest.mark.asyncio
    async def test_full_pipeline_file_to_db(self, tmp_path, mock_session):
        """Parse JSONL.gz -> extract ASINs -> submit via DiscoveryPipeline."""
        from cps.discovery.pipeline import DiscoveryPipeline
        from cps.seeds.dataset_importer import (
            extract_asins_from_metadata,
            submit_asins_in_batches,
        )

        # Create test dataset with 5 unique ASINs
        records = [
            {"parent_asin": "B08N5WRWNW", "title": "Product A"},
            {"parent_asin": "B09V3KXJPB", "title": "Product B"},
            {"parent_asin": "B07XJ8C8F5", "title": "Product C"},
            {"parent_asin": "B08N5WRWNW", "title": "Product A dup"},  # dup
            {"parent_asin": "B0BSHF7WHZ", "title": "Product D"},
            {"parent_asin": "B0D1XD1ZV3", "title": "Product E"},
        ]
        file_path = tmp_path / "meta_test.jsonl.gz"
        with gzip.open(file_path, "wt", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        pipeline = DiscoveryPipeline(mock_session)
        asins = extract_asins_from_metadata(file_path)

        result = await submit_asins_in_batches(
            pipeline, asins, batch_size=3
        )

        # 5 unique ASINs, batch_size=3 -> 2 batches
        assert result.total == 5
        assert result.batches == 2
        assert result.submitted == 5
        assert result.skipped == 0
