"""Spike: Harvest ASINs from Reddit deal subreddits via JSON API.

Reddit's public JSON API (append .json to any listing URL) returns post data
including URLs. Many deal posts link directly to amazon.com/dp/{ASIN}.

Target subreddits:
  - r/buildapcsales  (~2M members, heavy Amazon links)
  - r/deals           (~600K members)
  - r/AmazonDeals     (~100K members)
  - r/electronics     (mixed, some Amazon links)

Usage:
    # Quick test - 1 subreddit, 2 pages
    python spikes/reddit_asin_harvester.py --test

    # Full harvest - all subreddits, paginate through history
    python spikes/reddit_asin_harvester.py --all

    # Single subreddit
    python spikes/reddit_asin_harvester.py --subreddit buildapcsales
"""

import argparse
import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# Amazon ASIN extraction from URLs
# Matches: amazon.com/dp/B0xxxxx, amazon.com/gp/product/B0xxxxx, amzn.to redirects
AMAZON_ASIN_RE = re.compile(
    r"amazon\.com/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", re.IGNORECASE
)

# Target subreddits with high Amazon deal link density
SUBREDDITS = [
    "buildapcsales",
    "deals",
    "AmazonDeals",
    "AmazonTopRated",
]

# Rate limiting: Reddit API allows ~60 req/min for unauthenticated
REQUEST_DELAY_S = 1.5
MAX_PAGES_PER_SUB = 40  # Reddit limits to ~1000 posts via pagination (40 x 25)

OUTPUT_DIR = Path("spikes/asin_harvest")

# Use a real browser User-Agent for Reddit JSON API
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) CPS-Research/1.0",
}


@dataclass
class HarvestStats:
    """Track harvest progress."""

    total_requests: int = 0
    total_posts_scanned: int = 0
    posts_with_amazon: int = 0
    unique_asins: set = field(default_factory=set)
    errors: int = 0
    start_time: float = 0.0

    def summary(self) -> str:
        elapsed = time.monotonic() - self.start_time if self.start_time else 0
        return (
            f"Requests: {self.total_requests} | "
            f"Posts scanned: {self.total_posts_scanned} | "
            f"Posts w/ Amazon: {self.posts_with_amazon} | "
            f"Unique ASINs: {len(self.unique_asins)} | "
            f"Errors: {self.errors} | "
            f"Time: {elapsed:.0f}s"
        )


def extract_asins_from_text(text: str) -> list[str]:
    """Extract Amazon ASINs from any text containing Amazon URLs."""
    matches = AMAZON_ASIN_RE.findall(text)
    # Deduplicate, uppercase
    seen = set()
    result = []
    for asin in matches:
        asin_upper = asin.upper()
        if asin_upper not in seen:
            seen.add(asin_upper)
            result.append(asin_upper)
    return result


async def fetch_reddit_listing(
    client: httpx.AsyncClient,
    subreddit: str,
    after: str | None,
    stats: HarvestStats,
) -> tuple[list[str], str | None]:
    """Fetch one page of Reddit listing and extract ASINs.

    Returns (asins, next_after_token).
    """
    url = f"https://www.reddit.com/r/{subreddit}/hot.json"
    params = {"limit": 100, "raw_json": 1}
    if after:
        params["after"] = after

    try:
        resp = await client.get(url, params=params, headers=HEADERS, timeout=15)
        stats.total_requests += 1

        if resp.status_code == 429:
            print(f"  [429] Rate limited, waiting 60s...")
            await asyncio.sleep(60)
            return [], after  # retry with same after token

        if resp.status_code != 200:
            print(f"  [{resp.status_code}] Error fetching r/{subreddit}")
            stats.errors += 1
            return [], None

        data = resp.json()
        children = data.get("data", {}).get("children", [])
        next_after = data.get("data", {}).get("after")

        asins = []
        for child in children:
            post = child.get("data", {})
            stats.total_posts_scanned += 1

            # Check post URL
            post_url = post.get("url", "")
            # Check selftext for Amazon links
            selftext = post.get("selftext", "")
            # Check title (sometimes has ASIN)
            title = post.get("title", "")

            combined = f"{post_url} {selftext} {title}"
            found = extract_asins_from_text(combined)

            if found:
                stats.posts_with_amazon += 1
                asins.extend(found)

        return asins, next_after

    except Exception as e:
        stats.errors += 1
        print(f"  [ERROR] r/{subreddit}: {e}")
        return [], None


async def harvest_subreddit(
    client: httpx.AsyncClient,
    subreddit: str,
    stats: HarvestStats,
    max_pages: int = MAX_PAGES_PER_SUB,
) -> set[str]:
    """Harvest ASINs from a subreddit by paginating through listings."""
    sub_asins: set[str] = set()
    after = None

    print(f"\n--- r/{subreddit} ---")

    # Also try different sort orders for more coverage
    sort_types = ["hot", "top", "new"]

    for sort_type in sort_types:
        after = None
        print(f"  Sort: {sort_type}")

        for page in range(1, max_pages + 1):
            asins, next_after = await fetch_reddit_listing(
                client, subreddit, after, stats
            )

            new_asins = set(asins) - stats.unique_asins
            sub_asins.update(asins)
            stats.unique_asins.update(asins)

            if page <= 3 or page % 10 == 0:
                print(
                    f"    p{page:2d}: {len(asins)} ASINs ({len(new_asins)} new) | "
                    f"Sub total: {len(sub_asins)}"
                )

            if not next_after:
                print(f"    End of r/{subreddit}/{sort_type} at page {page}")
                break

            after = next_after
            await asyncio.sleep(REQUEST_DELAY_S)

    return sub_asins


async def harvest_all(subreddits: list[str]):
    """Harvest ASINs from all specified subreddits."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats = HarvestStats(start_time=time.monotonic())
    all_asins: set[str] = set()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for i, sub in enumerate(subreddits, 1):
            print(f"\n[{i}/{len(subreddits)}] Harvesting r/{sub}")
            sub_asins = await harvest_subreddit(client, sub, stats)
            all_asins.update(sub_asins)

            # Save per-subreddit file
            sub_file = OUTPUT_DIR / f"reddit_{sub}.txt"
            sub_file.write_text("\n".join(sorted(sub_asins)) + "\n")
            print(f"  Saved: {len(sub_asins)} ASINs to {sub_file}")

    # Final output
    output_file = OUTPUT_DIR / "reddit_all_asins.txt"
    output_file.write_text("\n".join(sorted(all_asins)) + "\n")

    print("\n" + "=" * 70)
    print(f"REDDIT HARVEST COMPLETE")
    print(f"Total unique ASINs: {len(all_asins)}")
    print(f"Output: {output_file}")
    print(f"Stats: {stats.summary()}")
    print("=" * 70)


async def test_mode():
    """Quick test: 1 subreddit, 2 pages."""
    print("=== TEST MODE: r/buildapcsales, 2 pages ===")
    stats = HarvestStats(start_time=time.monotonic())

    async with httpx.AsyncClient(follow_redirects=True) as client:
        after = None
        for page in range(1, 3):
            asins, after = await fetch_reddit_listing(
                client, "buildapcsales", after, stats
            )
            print(f"Page {page}: {len(asins)} ASINs -> {asins[:5]}")
            stats.unique_asins.update(asins)
            await asyncio.sleep(REQUEST_DELAY_S)

    print(f"\nTest result: {len(stats.unique_asins)} unique ASINs")
    print(f"Stats: {stats.summary()}")


def main():
    parser = argparse.ArgumentParser(description="Harvest ASINs from Reddit deals")
    parser.add_argument("--test", action="store_true", help="Quick test (2 pages)")
    parser.add_argument("--subreddit", type=str, help="Single subreddit")
    parser.add_argument("--all", action="store_true", help="All deal subreddits")
    args = parser.parse_args()

    if args.test:
        asyncio.run(test_mode())
    elif args.subreddit:
        asyncio.run(harvest_all([args.subreddit]))
    elif args.all:
        asyncio.run(harvest_all(SUBREDDITS))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
