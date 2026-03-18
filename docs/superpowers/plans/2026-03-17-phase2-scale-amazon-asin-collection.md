# Phase 2: Scale Amazon ASIN Collection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scale Amazon product coverage from ~8K to 500K+ ASINs by importing candidates from the UCSD Amazon Reviews 2023 academic dataset, then validating them through the existing CCC chart crawl pipeline.

**Architecture:** New `DatasetImporter` service downloads category metadata JSONL from HuggingFace/UCSD, extracts unique `parent_asin` values, and feeds them through the existing `DiscoveryPipeline.submit_candidates()`. Workers validate by fetching CCC charts — products with data become active, products without data get deactivated. A new CLI command `cps seed import-dataset` orchestrates the process.

**Tech Stack:** Python 3.12+, `httpx` (already available via `curl-cffi`), gzip/jsonlines parsing, existing SQLAlchemy async + DiscoveryPipeline

**Spec reference:** `docs/superpowers/specs/2026-03-17-distributed-crawling-design.md` Section 5 Phase 2

**Prerequisite:** Phase 1B merged to main, 308 tests passing. VPS needs `alembic upgrade head` for migration 003.

---

## Context: Why This Approach

The Amazon category sitemap (`amazon.com/sitemap-index.xml`) returns 500 and has no Sitemap references in robots.txt. Amazon explicitly blocks AI bots. Therefore, we use the **UCSD Amazon Reviews 2023 dataset** (McAuley Lab, hosted on HuggingFace) which contains **48.19M unique products** with `parent_asin` fields across 33 categories.

Strategy: extract ASINs → submit as candidates → CCC chart fetch validates them → active products enter the regular crawl rotation.

At 6 workers × 1 req/s = ~518K validations/day → 500K candidates validated in ~1 day.

---

## File Structure

### New files (4)

| File | Responsibility |
|------|---------------|
| `src/cps/seeds/dataset_importer.py` | Download UCSD JSONL.gz, stream-parse `parent_asin`, deduplicate, yield batches |
| `tests/unit/test_dataset_importer.py` | Parsing, dedup, batch yielding, error handling |
| `scripts/download_ucsd_metadata.sh` | Helper script to download specific category metadata files |
| `data/datasets/.gitkeep` | Directory for downloaded dataset files |

### Modified files (3)

| File | Change |
|------|--------|
| `src/cps/cli.py` | Add `cps seed import-dataset` command |
| `src/cps/discovery/pipeline.py` | Add `bestbuy` to `_PLATFORM_VALIDATORS` (prep for Phase 2 Best Buy) |
| `tests/unit/test_discovery_pipeline.py` | Add Best Buy validation tests |

### No new dependencies needed

- `gzip` — stdlib
- `json` — stdlib
- `httpx` — already available (used by curl_cffi internally), but we use stdlib `urllib.request` for simplicity since this is a one-time bulk download, not a crawl
- If download files are pre-staged locally, no HTTP client needed at all

---

## Task 1: Dataset Importer — Core Parser

**Files:**
- Create: `src/cps/seeds/dataset_importer.py`
- Test: `tests/unit/test_dataset_importer.py`

This task builds the core JSONL.gz parser that extracts unique ASINs from UCSD metadata files.

- [ ] **Step 1: Write failing tests for ASIN extraction**

```python
# tests/unit/test_dataset_importer.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_dataset_importer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.seeds.dataset_importer'`

- [ ] **Step 3: Implement extract_asins_from_metadata**

```python
# src/cps/seeds/dataset_importer.py
"""Import ASINs from UCSD Amazon Reviews 2023 metadata files.

The dataset (McAuley Lab, HuggingFace) contains 48.19M products across
33 categories. Metadata files are gzip-compressed JSONL with `parent_asin`
as the product identifier.

Download files from:
  https://datarepo.eng.ucsd.edu/mcauley_group/data/amazon_2023/raw/
  Subset: raw/meta_categories/<Category>.jsonl.gz
"""

import gzip
import json
import re
from collections.abc import Iterator
from pathlib import Path

import structlog

log = structlog.get_logger()

# Amazon ASIN: 10 alphanumeric characters (B0 prefix typical but not required)
_ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")


def extract_asins_from_metadata(file_path: Path) -> Iterator[str]:
    """Stream-parse a UCSD metadata JSONL.gz file and yield unique valid ASINs.

    Yields deduplicated ASINs in encounter order. Skips:
    - Records without `parent_asin`
    - Empty ASIN values
    - Invalid ASIN format (not 10 alphanumeric chars)
    - Malformed JSON lines
    """
    seen: set[str] = set()
    line_count = 0
    error_count = 0

    with gzip.open(file_path, "rt", encoding="utf-8") as f:
        for line in f:
            line_count += 1
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                error_count += 1
                continue

            asin = record.get("parent_asin", "")
            if not asin or not _ASIN_PATTERN.match(asin):
                continue

            if asin not in seen:
                seen.add(asin)
                yield asin

    log.info(
        "dataset_parsed",
        file=str(file_path.name),
        lines=line_count,
        unique_asins=len(seen),
        errors=error_count,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_dataset_importer.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/seeds/dataset_importer.py tests/unit/test_dataset_importer.py
git commit -m "feat: add UCSD dataset ASIN extractor with dedup and validation"
```

---

## Task 2: Batch Submission Helper

**Files:**
- Modify: `src/cps/seeds/dataset_importer.py`
- Test: `tests/unit/test_dataset_importer.py`

The `DiscoveryPipeline.submit_candidates()` works in-memory with a list. For 500K+ ASINs, we need to batch submissions to avoid OOM and provide progress feedback.

- [ ] **Step 1: Write failing tests for batch submission**

```python
# Append to tests/unit/test_dataset_importer.py

from unittest.mock import AsyncMock, MagicMock, patch

from cps.seeds.dataset_importer import submit_asins_in_batches


class TestSubmitAsinsInBatches:
    @pytest.fixture
    def mock_pipeline(self):
        from cps.discovery.pipeline import SubmitResult
        pipeline = AsyncMock()
        # Realistic mock: return submitted count matching actual batch size
        pipeline.submit_candidates = AsyncMock(side_effect=[
            SubmitResult(submitted=100, skipped=0, total=100),
            SubmitResult(submitted=100, skipped=0, total=100),
            SubmitResult(submitted=50, skipped=0, total=50),
        ])
        return pipeline

    async def test_submits_in_batches(self, mock_pipeline):
        asins = [f"B{str(i).zfill(9)}" for i in range(250)]
        result = await submit_asins_in_batches(mock_pipeline, iter(asins), batch_size=100)

        assert mock_pipeline.submit_candidates.call_count == 3
        assert result.submitted == 250  # 100 + 100 + 50
        assert result.total == 250      # ASINs consumed from iterator

    async def test_respects_max_candidates(self, mock_pipeline):
        from cps.discovery.pipeline import SubmitResult
        mock_pipeline.submit_candidates = AsyncMock(side_effect=[
            SubmitResult(submitted=100, skipped=0, total=100),
            SubmitResult(submitted=100, skipped=0, total=100),
        ])
        asins = [f"B{str(i).zfill(9)}" for i in range(500)]
        result = await submit_asins_in_batches(
            mock_pipeline, iter(asins), batch_size=100, max_candidates=200
        )

        assert mock_pipeline.submit_candidates.call_count == 2
        assert result.total == 200

    async def test_empty_iterator(self, mock_pipeline):
        mock_pipeline.submit_candidates = AsyncMock()  # reset side_effect
        result = await submit_asins_in_batches(mock_pipeline, iter([]))
        assert result.submitted == 0
        assert result.total == 0
        assert mock_pipeline.submit_candidates.call_count == 0

    async def test_accumulates_skipped(self, mock_pipeline):
        from cps.discovery.pipeline import SubmitResult
        mock_pipeline.submit_candidates = AsyncMock(
            return_value=SubmitResult(submitted=80, skipped=20, total=100)
        )
        asins = [f"B{str(i).zfill(9)}" for i in range(100)]
        result = await submit_asins_in_batches(mock_pipeline, iter(asins), batch_size=100)
        assert result.submitted == 80
        assert result.skipped == 20
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_dataset_importer.py::TestSubmitAsinsInBatches -v`
Expected: FAIL — `ImportError: cannot import name 'submit_asins_in_batches'`

- [ ] **Step 3: Implement submit_asins_in_batches**

```python
# Append to src/cps/seeds/dataset_importer.py
# Add to imports section: from dataclasses import dataclass
# Add to imports section: from cps.discovery.pipeline import DiscoveryPipeline, SubmitResult
# (Iterator is already imported from Task 1)


@dataclass(frozen=True)
class BatchSubmitResult:
    """Aggregate result across all batches."""
    submitted: int
    skipped: int
    total: int
    batches: int


async def submit_asins_in_batches(
    pipeline: DiscoveryPipeline,
    asins: Iterator[str],
    batch_size: int = 1000,
    max_candidates: int | None = None,
    platform: str = "amazon",
    priority: int = 2,
) -> BatchSubmitResult:
    """Submit ASINs to DiscoveryPipeline in batches.

    Reads from the iterator in chunks of `batch_size`, submitting each
    chunk via pipeline.submit_candidates(). Stops after `max_candidates`
    total if specified.
    """
    total_submitted = 0
    total_skipped = 0
    total_count = 0
    batch_count = 0

    batch: list[str] = []
    for asin in asins:
        if max_candidates is not None and total_count >= max_candidates:
            break
        batch.append(asin)
        total_count += 1

        if len(batch) >= batch_size:
            result = await pipeline.submit_candidates(batch, platform=platform, priority=priority)
            total_submitted += result.submitted
            total_skipped += result.skipped
            batch_count += 1
            log.info("batch_submitted", batch=batch_count, submitted=result.submitted, skipped=result.skipped)
            batch = []

    # Final partial batch
    if batch:
        result = await pipeline.submit_candidates(batch, platform=platform, priority=priority)
        total_submitted += result.submitted
        total_skipped += result.skipped
        batch_count += 1
        log.info("batch_submitted", batch=batch_count, submitted=result.submitted, skipped=result.skipped)

    return BatchSubmitResult(
        submitted=total_submitted,
        skipped=total_skipped,
        total=total_count,
        batches=batch_count,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_dataset_importer.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/seeds/dataset_importer.py tests/unit/test_dataset_importer.py
git commit -m "feat: add batch ASIN submission with progress logging"
```

---

## Task 3: CLI Command — `cps seed import-dataset`

**Files:**
- Modify: `src/cps/cli.py`

Adds a CLI command that ties together file parsing + batch submission.

- [ ] **Step 1: Write the CLI command**

Add to `src/cps/cli.py` after the existing `seed_stats` command (~line 131):

```python
@seed_app.command("import-dataset")
def seed_import_dataset(
    file: Path = typer.Option(..., "--file", "-f", help="Path to UCSD metadata JSONL.gz file"),
    batch_size: int = typer.Option(1000, "--batch-size", "-b", help="ASINs per batch"),
    max_candidates: int = typer.Option(0, "--max", "-m", help="Max ASINs to import (0=unlimited)"),
    priority: int = typer.Option(2, "--priority", help="Crawl priority for imported ASINs"),
    platform: str = typer.Option("amazon", "--platform", "-p", help="Platform for these products"),
) -> None:
    """Import ASINs from a UCSD Amazon Reviews 2023 metadata JSONL.gz file.

    Download metadata files from:
    https://datarepo.eng.ucsd.edu/mcauley_group/data/amazon_2023/raw/meta_categories/
    """
    if not file.exists():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(1)

    settings = get_settings()
    _configure_logging(settings.log_level, settings.log_format)

    async def _do():
        from cps.db.session import create_session_factory
        from cps.discovery.pipeline import DiscoveryPipeline
        from cps.seeds.dataset_importer import (
            extract_asins_from_metadata,
            submit_asins_in_batches,
        )

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            pipeline = DiscoveryPipeline(session)
            asins = extract_asins_from_metadata(file)

            result = await submit_asins_in_batches(
                pipeline,
                asins,
                batch_size=batch_size,
                max_candidates=max_candidates if max_candidates > 0 else None,
                platform=platform,
                priority=priority,
            )
            await session.commit()

        typer.echo(
            f"Dataset import complete: {result.submitted} added, "
            f"{result.skipped} skipped, {result.total} total "
            f"({result.batches} batches)"
        )

    _run_async(_do())
```

- [ ] **Step 2: Test manually (dry run)**

Run: `uv run cps seed import-dataset --help`
Expected: Shows usage with `--file`, `--batch-size`, `--max`, `--priority`, `--platform` options

- [ ] **Step 3: Run full test suite to verify no regressions**

Run: `uv run pytest -x -q`
Expected: 308+ tests pass, no failures

- [ ] **Step 4: Commit**

```bash
git add src/cps/cli.py
git commit -m "feat: add 'cps seed import-dataset' CLI for UCSD metadata import"
```

---

## Task 4: Best Buy Platform ID Validator (Prep)

**Files:**
- Modify: `src/cps/discovery/pipeline.py`
- Modify: `tests/unit/test_discovery_pipeline.py`

Even though Best Buy fetcher/parser are deferred, adding the validator now is zero-risk and unblocks future work.

- [ ] **Step 1: Write failing tests for Best Buy validation**

Append to `tests/unit/test_discovery_pipeline.py`:

```python
class TestValidateBestBuySku:
    def test_valid_7_digit_sku(self):
        assert validate_platform_id("6525401", "bestbuy") is True

    def test_valid_7_digit_sku_all_zeros(self):
        assert validate_platform_id("0000001", "bestbuy") is True

    def test_invalid_sku_too_short(self):
        assert validate_platform_id("65254", "bestbuy") is False

    def test_invalid_sku_too_long(self):
        assert validate_platform_id("65254019", "bestbuy") is False

    def test_invalid_sku_letters(self):
        assert validate_platform_id("652540A", "bestbuy") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_discovery_pipeline.py::TestValidateBestBuySku -v`
Expected: FAIL — `ValueError: Unknown platform: bestbuy`

- [ ] **Step 3: Add bestbuy validator**

In `src/cps/discovery/pipeline.py`, change line 15-17:

```python
_PLATFORM_VALIDATORS = {
    "amazon": re.compile(r"^[A-Z0-9]{10}$"),
    "bestbuy": re.compile(r"^\d{7}$"),
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_discovery_pipeline.py -v`
Expected: All tests PASS (existing + 5 new)

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/cps/discovery/pipeline.py tests/unit/test_discovery_pipeline.py
git commit -m "feat: add Best Buy SKU validator (7-digit) to discovery pipeline"
```

---

## Task 5: Download Helper Script

**Files:**
- Create: `scripts/download_ucsd_metadata.sh`

Provides a ready-to-use script for downloading the UCSD metadata files for high-value categories.

- [ ] **Step 1: Create the download script**

```bash
#!/usr/bin/env bash
# Download UCSD Amazon Reviews 2023 metadata files for ASIN extraction.
#
# Usage:
#   ./scripts/download_ucsd_metadata.sh [category...]
#   ./scripts/download_ucsd_metadata.sh              # downloads all priority categories
#   ./scripts/download_ucsd_metadata.sh Electronics  # downloads one category
#
# Files are saved to data/datasets/
# Source: https://datarepo.eng.ucsd.edu/mcauley_group/data/amazon_2023/raw/meta_categories/

set -euo pipefail

BASE_URL="https://datarepo.eng.ucsd.edu/mcauley_group/data/amazon_2023/raw/meta_categories"
OUT_DIR="data/datasets"

# Priority categories (high product count, relevant to price monitoring)
DEFAULT_CATEGORIES=(
    "Electronics"
    "Home_and_Kitchen"
    "Tools_and_Home_Improvement"
    "Toys_and_Games"
    "Cell_Phones_and_Accessories"
    "Sports_and_Outdoors"
    "Automotive"
    "Appliances"
    "Office_Products"
    "Video_Games"
)

mkdir -p "$OUT_DIR"

categories=("${@:-${DEFAULT_CATEGORIES[@]}}")

echo "Downloading ${#categories[@]} category metadata files to $OUT_DIR/"
echo ""

for cat in "${categories[@]}"; do
    filename="meta_${cat}.jsonl.gz"
    url="${BASE_URL}/${filename}"
    dest="${OUT_DIR}/${filename}"

    if [ -f "$dest" ]; then
        echo "SKIP  $filename (already exists)"
        continue
    fi

    echo "GET   $filename ..."
    curl -L -o "$dest" "$url" --progress-bar
    echo "  OK  $(du -h "$dest" | cut -f1)"
done

echo ""
echo "Done. Import with:"
echo "  cps seed import-dataset --file $OUT_DIR/meta_Electronics.jsonl.gz --max 50000"
```

- [ ] **Step 2: Make executable and create data directory**

```bash
chmod +x scripts/download_ucsd_metadata.sh
mkdir -p data/datasets
touch data/datasets/.gitkeep
```

- [ ] **Step 3: Verify .gitignore excludes dataset files**

Check that `data/` or `*.jsonl.gz` is in `.gitignore`. If not, add:

```
# Dataset files (large, downloaded separately)
data/datasets/*.jsonl.gz
```

- [ ] **Step 4: Commit**

```bash
git add scripts/download_ucsd_metadata.sh data/datasets/.gitkeep .gitignore
git commit -m "feat: add UCSD metadata download script for ASIN collection"
```

---

## Task 6: Multi-File Import Support

**Files:**
- Modify: `src/cps/seeds/dataset_importer.py`
- Test: `tests/unit/test_dataset_importer.py`

Support importing from multiple category files in one command (a directory of `.jsonl.gz` files).

- [ ] **Step 1: Write failing test for multi-file extraction**

```python
# Append to tests/unit/test_dataset_importer.py

from cps.seeds.dataset_importer import extract_asins_from_directory


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_dataset_importer.py::TestExtractAsinsFromDirectory -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement extract_asins_from_directory**

Add to `src/cps/seeds/dataset_importer.py`:

```python
def extract_asins_from_directory(dir_path: Path) -> Iterator[str]:
    """Extract unique ASINs from all .jsonl.gz files in a directory.

    Deduplicates across files. Processes files in sorted order for determinism.
    """
    seen: set[str] = set()
    files = sorted(dir_path.glob("*.jsonl.gz"))

    if not files:
        log.warning("no_dataset_files", directory=str(dir_path))
        return

    log.info("scanning_directory", directory=str(dir_path), file_count=len(files))

    for file_path in files:
        for asin in extract_asins_from_metadata(file_path):
            if asin not in seen:
                seen.add(asin)
                yield asin

    log.info("directory_scan_complete", total_unique=len(seen))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_dataset_importer.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Update CLI to support directory input**

In `src/cps/cli.py`, update the `seed_import_dataset` command — change the `--file` option:

```python
@seed_app.command("import-dataset")
def seed_import_dataset(
    file: Path = typer.Option(None, "--file", "-f", help="Path to JSONL.gz file"),
    directory: Path = typer.Option(None, "--dir", "-d", help="Path to directory of JSONL.gz files"),
    batch_size: int = typer.Option(1000, "--batch-size", "-b", help="ASINs per batch"),
    max_candidates: int = typer.Option(0, "--max", "-m", help="Max ASINs to import (0=unlimited)"),
    priority: int = typer.Option(2, "--priority", help="Crawl priority for imported ASINs"),
    platform: str = typer.Option("amazon", "--platform", "-p", help="Platform for these products"),
) -> None:
    """Import ASINs from UCSD Amazon Reviews 2023 metadata files."""
    if file is None and directory is None:
        typer.echo("Error: provide --file or --dir", err=True)
        raise typer.Exit(1)
    if file is not None and not file.exists():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(1)
    if directory is not None and not directory.is_dir():
        typer.echo(f"Error: Not a directory: {directory}", err=True)
        raise typer.Exit(1)

    settings = get_settings()
    _configure_logging(settings.log_level, settings.log_format)

    async def _do():
        from cps.db.session import create_session_factory
        from cps.discovery.pipeline import DiscoveryPipeline
        from cps.seeds.dataset_importer import (
            extract_asins_from_directory,
            extract_asins_from_metadata,
            submit_asins_in_batches,
        )

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            pipeline = DiscoveryPipeline(session)

            if file is not None:
                asins = extract_asins_from_metadata(file)
            else:
                asins = extract_asins_from_directory(directory)

            result = await submit_asins_in_batches(
                pipeline,
                asins,
                batch_size=batch_size,
                max_candidates=max_candidates if max_candidates > 0 else None,
                platform=platform,
                priority=priority,
            )
            await session.commit()

        typer.echo(
            f"Dataset import complete: {result.submitted} added, "
            f"{result.skipped} skipped, {result.total} total "
            f"({result.batches} batches)"
        )

    _run_async(_do())
```

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/cps/seeds/dataset_importer.py tests/unit/test_dataset_importer.py src/cps/cli.py
git commit -m "feat: add multi-file dataset import with directory support"
```

---

## Task 7: Crawl Status Enhancement — Platform Breakdown

**Files:**
- Modify: `src/cps/cli.py`

As we scale to 500K+ products, the status command needs per-platform breakdown.

- [ ] **Step 1: Update crawl_status to show per-platform stats**

Replace the `crawl_status` function in `src/cps/cli.py` (lines 184-240):

```python
@crawl_app.command("status")
def crawl_status() -> None:
    """Show crawl progress report with per-platform breakdown."""
    settings = get_settings()

    async def _do():
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import func, select

        from cps.db.models import CrawlTask, FetchRun, Product
        from cps.db.session import create_session_factory

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            # Per-platform product counts
            platform_counts = await session.execute(
                select(Product.platform, Product.is_active, func.count())
                .group_by(Product.platform, Product.is_active)
            )
            platform_rows = platform_counts.all()

            # Per-platform task status
            task_status = await session.execute(
                select(CrawlTask.platform, CrawlTask.status, func.count())
                .group_by(CrawlTask.platform, CrawlTask.status)
            )
            task_rows = task_status.all()

            # 24h throughput per platform
            cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
            throughput = await session.execute(
                select(CrawlTask.platform, func.count())
                .where(
                    CrawlTask.status == "completed",
                    CrawlTask.completed_at >= cutoff_24h,
                )
                .group_by(CrawlTask.platform)
            )
            throughput_rows = dict(throughput.all())

            # Extraction quality per platform
            quality = await session.execute(
                select(
                    FetchRun.platform,
                    func.count(),
                    func.count().filter(FetchRun.validation_passed == True),  # noqa: E712
                )
                .group_by(FetchRun.platform)
            )
            quality_rows = quality.all()

        # Display
        typer.echo("=== Products ===")
        typer.echo("Platform  | Active | Inactive")
        typer.echo("----------|--------|--------")
        platforms = {}
        for platform, is_active, count in platform_rows:
            if platform not in platforms:
                platforms[platform] = {"active": 0, "inactive": 0}
            key = "active" if is_active else "inactive"
            platforms[platform][key] = count
        for platform, counts in sorted(platforms.items()):
            typer.echo(f"{platform:10s}| {counts['active']:>6} | {counts['inactive']:>6}")

        typer.echo("")
        typer.echo("=== Task Status ===")
        typer.echo("Platform  | Status       | Count")
        typer.echo("----------|--------------|------")
        for platform, status, count in sorted(task_rows):
            typer.echo(f"{platform:10s}| {status:13s}| {count}")

        typer.echo("")
        typer.echo("=== 24h Throughput ===")
        for platform, count in sorted(throughput_rows.items()):
            typer.echo(f"{platform}: {count} completed")
        if not throughput_rows:
            typer.echo("(no completions in last 24h)")

        typer.echo("")
        typer.echo("=== Extraction Quality ===")
        for platform, total, passed in quality_rows:
            rate = (passed / total * 100) if total > 0 else 0
            typer.echo(f"{platform}: {rate:.1f}% ({passed}/{total})")
        if not quality_rows:
            typer.echo("(no extractions yet)")

    _run_async(_do())
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add src/cps/cli.py
git commit -m "feat: enhance crawl status with per-platform breakdown"
```

---

## Task 8: End-to-End Integration Test

**Files:**
- Modify: `tests/unit/test_dataset_importer.py`

Integration-style test that verifies the full pipeline: parse file → batch submit → verify products + crawl tasks created.

- [ ] **Step 1: Write integration test**

```python
# Append to tests/unit/test_dataset_importer.py

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

    async def test_full_pipeline_file_to_db(self, tmp_path, mock_session):
        """Parse JSONL.gz → extract ASINs → submit via DiscoveryPipeline."""
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

        # 5 unique ASINs, batch_size=3 → 2 batches
        assert result.total == 5
        assert result.batches == 2
        assert result.submitted == 5
        assert result.skipped == 0
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/unit/test_dataset_importer.py::TestDatasetImportIntegration -v`
Expected: PASS

- [ ] **Step 3: Run full test suite with coverage**

Run: `uv run pytest --cov=cps --cov-report=term-missing -q`
Expected: All tests pass, coverage ≥ 80%

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_dataset_importer.py
git commit -m "test: add integration test for dataset import pipeline"
```

---

## Execution Summary

| Task | Description | Est. |
|------|-------------|------|
| 1 | ASIN extractor (JSONL.gz parser) | 5 min |
| 2 | Batch submission helper | 5 min |
| 3 | CLI `seed import-dataset` command | 3 min |
| 4 | Best Buy SKU validator (prep) | 3 min |
| 5 | Download helper script | 3 min |
| 6 | Multi-file/directory support | 5 min |
| 7 | Crawl status per-platform breakdown | 3 min |
| 8 | End-to-end integration test | 3 min |
| **Total** | | **~30 min** |

## Post-Implementation: VPS Deployment Steps

After all tasks pass:

1. **Download datasets on VPS:**
   ```bash
   scp scripts/download_ucsd_metadata.sh vps:~/cps/
   ssh vps "cd ~/cps && ./scripts/download_ucsd_metadata.sh Electronics Home_and_Kitchen"
   ```

2. **Import small batch first (validation):**
   ```bash
   cps seed import-dataset --file data/datasets/meta_Electronics.jsonl.gz --max 100
   cps crawl run --limit 100
   cps crawl status  # check hit rate
   ```

3. **If hit rate > 10%, scale up:**
   ```bash
   cps seed import-dataset --dir data/datasets/ --max 500000
   ```

4. **Start workers:**
   ```bash
   cps worker run --platform amazon  # run 6 instances via Docker Compose
   ```

5. **Monitor:**
   ```bash
   cps crawl status  # per-platform breakdown
   cps db stats      # row counts + disk usage
   ```
