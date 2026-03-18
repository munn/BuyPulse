"""Spike: Test curl_cffi against CCC Cloudflare TLS fingerprint detection.

Goal: Download 15+ CCC chart images at 1 req/s and observe if Cloudflare blocks us.
Compare: httpx (known to get blocked after ~15 requests) vs curl_cffi (Chrome TLS fingerprint).
"""

import asyncio
import time
from pathlib import Path

from curl_cffi.requests import AsyncSession

BASE_URL = "https://charts.camelcamelcamel.com/us"
QUERY_PARAMS = {
    "force": "1",
    "zero": "0",
    "w": "855",
    "h": "513",
    "desired": "false",
    "legend": "1",
    "ilt": "1",
    "tp": "all",
    "fo": "0",
    "lang": "en",
}

# Mix of popular ASINs for testing
TEST_ASINS = [
    "B0DJM1ZV5J",  # iPad Air
    "B0D1XD1ZV3",  # AirPods Pro 2
    "B0CHX1W1XY",  # iPhone case
    "B0BSHF7WHW",  # USB-C hub
    "B09V3KXJPB",  # Fire TV Stick
    "B08N5WRWNW",  # Echo Dot
    "B0D5B9V3XQ",  # Kindle Paperwhite
    "B0CX23V2ZK",  # Echo Show
    "B0BT2KFJ2V",  # Blink camera
    "B07FZ8S74R",  # Echo Buds
    "B09JQL3NWT",  # Anker charger
    "B0C8PSRWFM",  # Samsung SSD
    "B0DGJGJK58",  # Logitech mouse
    "B0D77BX6LV",  # Sony headphones
    "B0DJZFX7DC",  # Apple Watch
    "B0BN72Y6WP",  # Roomba
    "B0CG1B94S3",  # Ring doorbell
    "B0BTFKXQFL",  # JBL speaker
    "B0CZSGWLD9",  # GoPro
    "B0D1222MRK",  # Fitbit
]

OUTPUT_DIR = Path("spikes/curl_cffi_results")


async def test_curl_cffi():
    """Download charts using curl_cffi with Chrome TLS impersonation."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    async with AsyncSession(impersonate="chrome") as session:
        for i, asin in enumerate(TEST_ASINS):
            url = f"{BASE_URL}/{asin}/amazon-new-used.png"
            start = time.monotonic()

            try:
                resp = await session.get(
                    url,
                    params=QUERY_PARAMS,
                    timeout=15,
                    allow_redirects=True,
                )
                elapsed = time.monotonic() - start
                status = resp.status_code
                size = len(resp.content) if resp.status_code == 200 else 0

                result = {
                    "index": i + 1,
                    "asin": asin,
                    "status": status,
                    "size_kb": round(size / 1024, 1),
                    "elapsed_s": round(elapsed, 2),
                }
                results.append(result)

                if status == 200 and size > 1000:
                    # Save successful downloads for verification
                    (OUTPUT_DIR / f"{asin}.png").write_bytes(resp.content)
                    print(f"[{i+1:2d}/20] {asin} -> {status} | {result['size_kb']}KB | {elapsed:.2f}s ✅")
                else:
                    print(f"[{i+1:2d}/20] {asin} -> {status} | {result['size_kb']}KB | {elapsed:.2f}s ❌")

            except Exception as e:
                elapsed = time.monotonic() - start
                result = {
                    "index": i + 1,
                    "asin": asin,
                    "status": "ERROR",
                    "error": str(e),
                    "elapsed_s": round(elapsed, 2),
                }
                results.append(result)
                print(f"[{i+1:2d}/20] {asin} -> ERROR: {e} | {elapsed:.2f}s ❌")

            # 1 req/s rate limit
            await asyncio.sleep(1.0)

    # Summary
    print("\n" + "=" * 60)
    successes = sum(1 for r in results if r.get("status") == 200 and r.get("size_kb", 0) > 1)
    blocks = sum(1 for r in results if r.get("status") == 403)
    rate_limits = sum(1 for r in results if r.get("status") == 429)
    errors = sum(1 for r in results if r.get("status") == "ERROR")

    print(f"Results: {successes} OK / {blocks} blocked / {rate_limits} rate-limited / {errors} errors")
    print(f"Success rate: {successes}/{len(results)} = {successes/len(results)*100:.0f}%")

    if blocks > 0:
        first_block = next(r["index"] for r in results if r.get("status") == 403)
        print(f"First block at request #{first_block}")

    if successes == len(results):
        print("🎉 curl_cffi passed! No Cloudflare blocks detected.")
    elif successes > 15:
        print("⚠️ Mostly working, some issues. Investigate failed requests.")
    else:
        print("💀 curl_cffi is also being blocked. Need alternative approach.")


if __name__ == "__main__":
    asyncio.run(test_curl_cffi())
