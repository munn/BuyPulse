#!/usr/bin/env bash
# Download UCSD Amazon Reviews 2023 metadata files for ASIN extraction.
#
# Usage:
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
