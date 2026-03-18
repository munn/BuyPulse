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
from dataclasses import dataclass
from pathlib import Path

import structlog

from cps.discovery.pipeline import DiscoveryPipeline

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


def extract_asins_from_directory(dir_path: Path) -> Iterator[str]:
    """Extract unique ASINs from all .jsonl.gz files in a directory.

    Deduplicates across files. Processes files in sorted order for determinism.
    Note: each file's extract_asins_from_metadata also deduplicates within that file;
    the cross-file seen set here handles duplicates that span multiple files.
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


@dataclass(frozen=True)
class BatchSubmitResult:
    """Aggregate result across all batches."""

    submitted: int
    skipped: int
    total: int  # ASINs consumed from iterator (already validated by parser)
    batches: int


async def submit_asins_in_batches(
    pipeline: DiscoveryPipeline,
    asins: Iterator[str],
    batch_size: int = 1000,
    max_candidates: int | None = None,
    platform: str = "amazon",
    priority: int = 2,
    commit_fn: object | None = None,
) -> BatchSubmitResult:
    """Submit ASINs to DiscoveryPipeline in batches.

    Reads from the iterator in chunks of `batch_size`, submitting each
    chunk via pipeline.submit_candidates(). Stops after `max_candidates`
    total if specified.

    If commit_fn is provided (an async callable), it is called after each
    batch to persist progress. This prevents data loss if the process
    crashes during a large import.
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
            if commit_fn is not None:
                await commit_fn()
            log.info(
                "batch_submitted",
                batch=batch_count,
                submitted=result.submitted,
                skipped=result.skipped,
            )
            batch = []

    # Final partial batch
    if batch:
        result = await pipeline.submit_candidates(batch, platform=platform, priority=priority)
        total_submitted += result.submitted
        total_skipped += result.skipped
        batch_count += 1
        if commit_fn is not None:
            await commit_fn()
        log.info(
            "batch_submitted",
            batch=batch_count,
            submitted=result.submitted,
            skipped=result.skipped,
        )

    return BatchSubmitResult(
        submitted=total_submitted,
        skipped=total_skipped,
        total=total_count,
        batches=batch_count,
    )
