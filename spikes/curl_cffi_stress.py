"""Stress test: Find Cloudflare blocking threshold with curl_cffi.

Phase 1: 30 requests at 1 req/s (safe baseline)
Phase 2: 20 requests at 2 req/s (push the limit)
Phase 3: 10 requests at 5 req/s (aggressive burst)

Observe where blocking starts.
"""

import asyncio
import time

from curl_cffi.requests import AsyncSession

BASE_URL = "https://charts.camelcamelcamel.com/us"
QUERY = "force=1&zero=0&w=855&h=513&desired=false&legend=1&ilt=1&tp=all&fo=0&lang=en"

# 60 diverse ASINs
ASINS = [
    "B0D1XD1ZV3", "B09V3KXJPB", "B0BSHF7WHW", "B07FZ8S74R", "B09JQL3NWT",
    "B0CX23V2ZK", "B08N5WRWNW", "B0CHX1W1XY", "B0BN72Y6WP", "B0CG1B94S3",
    "B0BTFKXQFL", "B0CZSGWLD9", "B0D1222MRK", "B0DJM1ZV5J", "B0DJZFX7DC",
    "B0D77BX6LV", "B0DGJGJK58", "B0C8PSRWFM", "B0BT2KFJ2V", "B0D5B9V3XQ",
    "B0931VRJT5", "B09B8DQ26F", "B0CL5KNB9M", "B0CFWQSDWQ", "B0BDJ279KF",
    "B0C1H26C46", "B0BTJ6KBVB", "B0BDHWDR12", "B09JQMJHXY", "B07ZPKN6YR",
    "B08BHXG144", "B0CHWRXH8B", "B0CJCJHXHF", "B09HSR83TV", "B0BXN2FK8P",
    "B0CSTJ2Y5F", "B0CY63ZJWT", "B0D4JRKNMD", "B0D24JKRM4", "B0CYPSNTT6",
    "B0DFDJHQ6Z", "B0DL13VQPZ", "B0DDRG9V47", "B0DDT7MFJH", "B0D9JG3QCP",
    "B0CJ4DKFRG", "B0CHML68V7", "B0CJ3F5FJP", "B0CMK3JWY1", "B0BQXKW8JN",
    "B0BRJM8BGY", "B0B7CPSN2K", "B09HN37XDT", "B0BG9433MV", "B0BG94CL5Y",
    "B0C75FL2PK", "B0CH54XPNW", "B0C4HSLJR3", "B0CX5C6SL7", "B0CR1JKLDL",
]


async def run_phase(session, asins, delay, phase_name):
    """Run a batch of requests at a given rate."""
    results = {"ok": 0, "blocked": 0, "rate_limited": 0, "error": 0, "no_data": 0}
    print(f"\n{'='*60}")
    print(f"Phase: {phase_name} | {len(asins)} requests | {1/delay:.1f} req/s")
    print(f"{'='*60}")

    for i, asin in enumerate(asins):
        url = f"{BASE_URL}/{asin}/amazon-new-used.png?{QUERY}"
        start = time.monotonic()

        try:
            resp = await session.get(url, timeout=15, allow_redirects=True)
            elapsed = time.monotonic() - start
            status = resp.status_code
            size = len(resp.content)

            if status == 200 and size > 15000:
                results["ok"] += 1
                tag = "✅"
            elif status == 200 and size <= 15000:
                results["no_data"] += 1
                tag = "📭 no-data"
            elif status == 403:
                results["blocked"] += 1
                tag = "🚫 BLOCKED"
            elif status == 429:
                results["rate_limited"] += 1
                tag = "⏳ RATE LIMITED"
            else:
                results["error"] += 1
                tag = f"❌ HTTP {status}"

            print(f"  [{i+1:2d}/{len(asins)}] {asin} → {status} | {size/1024:.0f}KB | {elapsed:.2f}s {tag}")

        except Exception as e:
            results["error"] += 1
            elapsed = time.monotonic() - start
            print(f"  [{i+1:2d}/{len(asins)}] {asin} → ERROR: {e} | {elapsed:.2f}s ❌")

        await asyncio.sleep(delay)

    print(f"\n  Summary: {results['ok']} chart / {results['no_data']} no-data / "
          f"{results['blocked']} blocked / {results['rate_limited']} rate-limited / {results['error']} error")
    return results


async def main():
    print("curl_cffi stress test — finding Cloudflare blocking threshold")
    print(f"Total ASINs: {len(ASINS)}")

    all_results = []

    async with AsyncSession(impersonate="chrome") as session:
        # Phase 1: safe rate
        r1 = await run_phase(session, ASINS[:30], delay=1.0, phase_name="1 req/s (safe)")
        all_results.append(("1 req/s", r1))

        # Phase 2: double speed
        r2 = await run_phase(session, ASINS[30:50], delay=0.5, phase_name="2 req/s (pushing)")
        all_results.append(("2 req/s", r2))

        # Phase 3: aggressive burst
        r3 = await run_phase(session, ASINS[50:60], delay=0.2, phase_name="5 req/s (aggressive)")
        all_results.append(("5 req/s", r3))

    # Final report
    print(f"\n{'='*60}")
    print("FINAL REPORT")
    print(f"{'='*60}")
    for rate, r in all_results:
        total = sum(r.values())
        blocked = r["blocked"] + r["rate_limited"]
        print(f"  {rate:>8s}: {r['ok']} chart + {r['no_data']} no-data / {total} total | {blocked} blocked")

    total_blocked = sum(r["blocked"] + r["rate_limited"] for _, r in all_results)
    if total_blocked == 0:
        print("\n🎉 No blocks at any speed!")
    else:
        print(f"\n⚠️ {total_blocked} blocks detected — check which phase triggered it")


if __name__ == "__main__":
    asyncio.run(main())
