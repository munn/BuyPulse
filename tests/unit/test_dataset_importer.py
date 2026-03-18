"""Tests for UCSD Amazon dataset ASIN extraction."""

import gzip
import json
from pathlib import Path

import pytest

from cps.seeds.dataset_importer import extract_asins_from_metadata


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
