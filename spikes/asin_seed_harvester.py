"""Spike: Harvest ASINs from CamelCamelCamel top_drops pages.

Approach: Crawl CCC's public top_drops listing pages to extract ASINs.
Each page has ~20 ASINs. Default view (no category filter) has ~420 pages.

Key finding from research (2026-03-17):
  - Category filters only work reliably for the first ~3-4 pages
  - After that, results converge to the global/default listing
  - Best strategy: crawl default view (all pages) + each category's first 5 pages
  - This maximizes unique ASINs while avoiding redundant requests

Estimated yield: 8,000-10,000 unique ASINs (all have CCC price history)
Time: ~10 minutes at 1.2 req/s (default 450 pages + 29 categories x 5 pages)

Usage:
    # Quick test - 3 pages to verify scraping works
    python spikes/asin_seed_harvester.py --test

    # Recommended: default view + category supplements (~10 min)
    python spikes/asin_seed_harvester.py --smart

    # Default view only, all pages
    python spikes/asin_seed_harvester.py --default-only

    # Single category, all pages
    python spikes/asin_seed_harvester.py --category electronics

    # All categories brute force (mostly redundant, ~3 hours)
    python spikes/asin_seed_harvester.py --all

    # Resume interrupted harvest
    python spikes/asin_seed_harvester.py --all --resume
"""

import argparse
import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from curl_cffi.requests import AsyncSession

# CCC top_drops URL pattern
BASE_URL = "https://camelcamelcamel.com/top_drops"

# ASIN regex: appears in /product/{ASIN} links on CCC pages
# ASINs are 10 chars: B0-prefixed product IDs or 10-digit ISBNs (all alphanumeric)
ASIN_RE = re.compile(r"/product/([A-Za-z0-9]{10})\b")

# All CCC categories (29 total)
# Slug format confirmed via testing: lowercase, no spaces/special chars
CATEGORIES = [
    "appliances",
    "artscraftssewing",
    "automotive",
    "baby",
    "beauty",
    "books",
    "cellphones",
    "clothing",
    "electronics",
    "grocery",
    "health",
    "homekitchen",
    "industrial",
    "jewelry",
    "kindle",
    "moviestv",
    "music",
    "musicalinstruments",
    "office",
    "other",
    "patio",
    "petsupplies",
    "shoes",
    "software",
    "sports",
    "tools",
    "toys",
    "videogames",
]

# Rate limiting
REQUEST_DELAY_S = 1.2  # slightly above 1 req/s for safety margin
MAX_CONSECUTIVE_EMPTY = 3  # stop after N consecutive empty pages (end of category)
MAX_RETRIES = 3

OUTPUT_DIR = Path("spikes/asin_harvest")
PROGRESS_FILE = OUTPUT_DIR / "progress.json"


@dataclass
class HarvestStats:
    """Track harvest progress and results."""

    total_requests: int = 0
    total_asins_found: int = 0
    unique_asins: set = field(default_factory=set)
    errors: int = 0
    rate_limited: int = 0
    blocked: int = 0
    categories_completed: list = field(default_factory=list)
    start_time: float = 0.0

    def summary(self) -> str:
        elapsed = time.monotonic() - self.start_time if self.start_time else 0
        return (
            f"Requests: {self.total_requests} | "
            f"ASINs found: {self.total_asins_found} | "
            f"Unique: {len(self.unique_asins)} | "
            f"Errors: {self.errors} | "
            f"429s: {self.rate_limited} | "
            f"403s: {self.blocked} | "
            f"Time: {elapsed:.0f}s"
        )


def extract_asins_from_html(html: str) -> list[str]:
    """Extract ASINs from CCC top_drops HTML page.

    ASINs appear in product links like: /product/B0DYJZSYWV?active=...
    """
    matches = ASIN_RE.findall(html)
    # Deduplicate while preserving order
    seen = set()
    result = []
    for asin in matches:
        if asin not in seen:
            seen.add(asin)
            result.append(asin)
    return result


async def fetch_page(
    session: AsyncSession,
    category: str,
    page: int,
    stats: HarvestStats,
) -> list[str]:
    """Fetch a single top_drops page and extract ASINs.

    Returns list of ASINs found, empty list on failure.
    """
    if category:
        url = f"{BASE_URL}?category={category}&p={page}"
    else:
        url = f"{BASE_URL}?p={page}"

    for attempt in range(MAX_RETRIES):
        try:
            resp = await session.get(
                url,
                timeout=15,
                allow_redirects=True,
            )
            stats.total_requests += 1

            if resp.status_code == 200:
                asins = extract_asins_from_html(resp.text)
                return asins

            if resp.status_code == 429:
                stats.rate_limited += 1
                wait = 30 * (attempt + 1)
                print(f"  [429] Rate limited on {category} p{page}, waiting {wait}s...")
                await asyncio.sleep(wait)
                continue

            if resp.status_code == 403:
                stats.blocked += 1
                wait = 60 * (attempt + 1)
                print(f"  [403] Blocked on {category} p{page}, waiting {wait}s...")
                await asyncio.sleep(wait)
                continue

            print(f"  [{resp.status_code}] Unexpected status for {category} p{page}")
            stats.errors += 1
            return []

        except Exception as e:
            stats.errors += 1
            print(f"  [ERROR] {category} p{page}: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(5)
            continue

    return []


def load_progress() -> dict:
    """Load progress from previous interrupted run."""
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"completed_categories": [], "all_asins": []}


def save_progress(stats: HarvestStats, all_asins: set):
    """Save progress for resume capability."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    progress = {
        "completed_categories": stats.categories_completed,
        "all_asins": sorted(all_asins),
        "stats": {
            "total_requests": stats.total_requests,
            "total_asins_found": stats.total_asins_found,
            "unique_count": len(all_asins),
            "errors": stats.errors,
            "rate_limited": stats.rate_limited,
            "blocked": stats.blocked,
        },
    }
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


async def harvest_category(
    session: AsyncSession,
    category: str,
    stats: HarvestStats,
    max_pages: int = 500,
) -> set[str]:
    """Harvest all ASINs from a single category.

    Stops when N consecutive empty pages are found (end of category).
    """
    category_asins = set()
    consecutive_empty = 0

    display_name = category if category else "default (all)"
    print(f"\n--- Category: {display_name} ---")

    for page in range(1, max_pages + 1):
        asins = await fetch_page(session, category, page, stats)

        if not asins:
            consecutive_empty += 1
            if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                print(f"  End of {category} at page {page} ({len(category_asins)} ASINs)")
                break
        else:
            consecutive_empty = 0
            new_asins = set(asins) - stats.unique_asins
            category_asins.update(asins)
            stats.unique_asins.update(asins)
            stats.total_asins_found += len(asins)

            if page % 20 == 0 or page <= 3:
                print(
                    f"  p{page:3d}: {len(asins)} ASINs ({len(new_asins)} new) | "
                    f"Category total: {len(category_asins)} | "
                    f"Global unique: {len(stats.unique_asins)}"
                )

        # Rate limiting
        await asyncio.sleep(REQUEST_DELAY_S)

    return category_asins


async def harvest_all(
    categories: list[str],
    resume: bool = False,
    max_pages: int = 500,
):
    """Harvest ASINs from all specified categories."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats = HarvestStats(start_time=time.monotonic())
    all_asins: set[str] = set()

    # Resume support
    skip_categories = set()
    if resume:
        progress = load_progress()
        skip_categories = set(progress.get("completed_categories", []))
        all_asins = set(progress.get("all_asins", []))
        stats.unique_asins = all_asins.copy()
        if skip_categories:
            print(f"Resuming: skipping {len(skip_categories)} completed categories")
            print(f"Loaded {len(all_asins)} previously harvested ASINs")

    async with AsyncSession(impersonate="chrome") as session:
        for i, category in enumerate(categories, 1):
            if category in skip_categories:
                print(f"[{i}/{len(categories)}] Skipping {category} (already done)")
                continue

            print(f"\n[{i}/{len(categories)}] Harvesting: {category}")
            category_asins = await harvest_category(
                session, category, stats, max_pages=max_pages
            )

            # Save per-category file
            cat_file = OUTPUT_DIR / f"{category}.txt"
            cat_file.write_text("\n".join(sorted(category_asins)) + "\n")

            stats.categories_completed.append(category)
            all_asins.update(category_asins)

            # Save progress after each category
            save_progress(stats, all_asins)
            print(f"  Saved: {len(category_asins)} ASINs to {cat_file}")
            print(f"  Running total: {stats.summary()}")

    # Final output
    output_file = OUTPUT_DIR / "all_asins.txt"
    output_file.write_text("\n".join(sorted(all_asins)) + "\n")

    print("\n" + "=" * 70)
    print(f"HARVEST COMPLETE")
    print(f"Total unique ASINs: {len(all_asins)}")
    print(f"Output: {output_file}")
    print(f"Stats: {stats.summary()}")
    print(f"Categories: {len(stats.categories_completed)}/{len(categories)}")
    print("=" * 70)

    return all_asins


async def test_mode():
    """Quick test: 1 category, 3 pages to verify scraping works."""
    print("=== TEST MODE: electronics, 3 pages ===")
    stats = HarvestStats(start_time=time.monotonic())

    async with AsyncSession(impersonate="chrome") as session:
        for page in range(1, 4):
            asins = await fetch_page(session, "electronics", page, stats)
            print(f"Page {page}: {len(asins)} ASINs -> {asins[:5]}...")
            stats.unique_asins.update(asins)
            await asyncio.sleep(REQUEST_DELAY_S)

    print(f"\nTest result: {len(stats.unique_asins)} unique ASINs from 3 pages")
    print(f"Stats: {stats.summary()}")

    # Save test output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    test_file = OUTPUT_DIR / "test_asins.txt"
    test_file.write_text("\n".join(sorted(stats.unique_asins)) + "\n")
    print(f"Saved to: {test_file}")


async def smart_harvest():
    """Recommended harvest: default view (all pages) + category supplements.

    Strategy:
    1. Crawl default view (no category filter) pages 1-500 (~420 pages of content)
    2. For each category, crawl pages 1-5 (category filters work for first few pages)
    3. This captures the maximum unique ASINs with minimal redundancy

    Expected: ~10 minutes, 8,000-10,000 unique ASINs
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats = HarvestStats(start_time=time.monotonic())
    all_asins: set[str] = set()

    async with AsyncSession(impersonate="chrome") as session:
        # Phase 1: Default view (no category filter) - all pages
        print("=" * 70)
        print("PHASE 1: Default view (all categories, all pages)")
        print("=" * 70)
        default_asins = await harvest_category(
            session, "", stats, max_pages=500  # empty string = no category param
        )
        all_asins.update(default_asins)

        default_file = OUTPUT_DIR / "default_all.txt"
        default_file.write_text("\n".join(sorted(default_asins)) + "\n")
        print(f"  Phase 1 done: {len(default_asins)} ASINs from default view")
        save_progress(stats, all_asins)

        # Phase 2: Category supplements (first 5 pages each)
        print("\n" + "=" * 70)
        print("PHASE 2: Category supplements (5 pages each)")
        print("=" * 70)

        for i, category in enumerate(CATEGORIES, 1):
            print(f"\n[{i}/{len(CATEGORIES)}] Category supplement: {category}")
            cat_asins = await harvest_category(
                session, category, stats, max_pages=5
            )
            new_count = len(cat_asins - all_asins)
            all_asins.update(cat_asins)

            if cat_asins:
                cat_file = OUTPUT_DIR / f"cat_{category}.txt"
                cat_file.write_text("\n".join(sorted(cat_asins)) + "\n")
                print(f"  {category}: {len(cat_asins)} ASINs ({new_count} new)")

            save_progress(stats, all_asins)

    # Final output
    output_file = OUTPUT_DIR / "all_asins.txt"
    output_file.write_text("\n".join(sorted(all_asins)) + "\n")

    print("\n" + "=" * 70)
    print("SMART HARVEST COMPLETE")
    print(f"Total unique ASINs: {len(all_asins)}")
    print(f"Output: {output_file}")
    print(f"Stats: {stats.summary()}")
    print("=" * 70)

    return all_asins


def main():
    parser = argparse.ArgumentParser(description="Harvest ASINs from CCC top_drops")
    parser.add_argument("--test", action="store_true", help="Quick test (3 pages)")
    parser.add_argument("--smart", action="store_true", help="Smart harvest (recommended)")
    parser.add_argument("--default-only", action="store_true", help="Default view only")
    parser.add_argument("--category", type=str, help="Harvest single category")
    parser.add_argument("--all", action="store_true", help="Harvest all categories")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted run")
    parser.add_argument("--max-pages", type=int, default=500, help="Max pages per cat")
    args = parser.parse_args()

    if args.test:
        asyncio.run(test_mode())
    elif args.smart:
        asyncio.run(smart_harvest())
    elif args.default_only:
        asyncio.run(harvest_all([""], max_pages=args.max_pages))
    elif args.category:
        asyncio.run(harvest_all([args.category], max_pages=args.max_pages))
    elif args.all:
        asyncio.run(
            harvest_all(CATEGORIES, resume=args.resume, max_pages=args.max_pages)
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
