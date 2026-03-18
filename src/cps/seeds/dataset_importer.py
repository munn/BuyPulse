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
