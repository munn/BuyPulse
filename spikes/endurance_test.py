"""24-hour endurance test: verify 1 req/s sustained crawling stability.

Run: nohup uv run python spikes/endurance_test.py &
Check: tail -f spikes/endurance_log.txt
Stop: kill $(cat spikes/endurance.pid)

Cycles through ~60 ASINs repeatedly at 1 req/s.
Prints hourly summary + final report.
"""

import asyncio
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi.requests import AsyncSession

BASE_URL = "https://charts.camelcamelcamel.com/us"
QUERY = "force=1&zero=0&w=855&h=513&desired=false&legend=1&ilt=1&tp=all&fo=0&lang=en"
DELAY = 1.0  # 1 req/s
DURATION_HOURS = 24

LOG_FILE = Path("spikes/endurance_log.txt")
PID_FILE = Path("spikes/endurance.pid")

ASINS = [
    "B0D1XD1ZV3", "B09V3KXJPB", "B0BSHF7WHW", "B07FZ8S74R", "B09JQL3NWT",
    "B0CX23V2ZK", "B08N5WRWNW", "B0CHX1W1XY", "B09B8DQ26F", "B0CL5KNB9M",
    "B0C1H26C46", "B0BDHWDR12", "B09JQMJHXY", "B07ZPKN6YR", "B08BHXG144",
    "B0CHWRXH8B", "B0931VRJT5", "B0BDJ279KF", "B0BTJ6KBVB", "B0CFWQSDWQ",
    "B0BN72Y6WP", "B0CG1B94S3", "B0BTFKXQFL", "B0CZSGWLD9", "B0D1222MRK",
    "B0DJM1ZV5J", "B0DJZFX7DC", "B0D77BX6LV", "B0DGJGJK58", "B0C8PSRWFM",
    "B0BT2KFJ2V", "B0D5B9V3XQ", "B0CJCJHXHF", "B09HSR83TV", "B0BXN2FK8P",
    "B0CSTJ2Y5F", "B0CY63ZJWT", "B0D4JRKNMD", "B0D24JKRM4", "B0CYPSNTT6",
    "B0DFDJHQ6Z", "B0DL13VQPZ", "B0DDRG9V47", "B0DDT7MFJH", "B0D9JG3QCP",
    "B0CJ4DKFRG", "B0CHML68V7", "B0CJ3F5FJP", "B0CMK3JWY1", "B0BQXKW8JN",
    "B0BRJM8BGY", "B0B7CPSN2K", "B09HN37XDT", "B0BG9433MV", "B0BG94CL5Y",
    "B0C75FL2PK", "B0CH54XPNW", "B0C4HSLJR3", "B0CX5C6SL7", "B0CR1JKLDL",
]

shutdown = False


def handle_signal(sig, frame):
    global shutdown
    shutdown = True


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


async def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Write PID for easy stopping
    PID_FILE.write_text(str(os.getpid()))

    log(f"Endurance test started — PID {os.getpid()}")
    log(f"Target: {DURATION_HOURS}h at {1/DELAY:.0f} req/s, cycling {len(ASINS)} ASINs")
    log(f"Stop: kill $(cat {PID_FILE})")

    totals = {"ok": 0, "no_data": 0, "rate_limited": 0, "blocked": 0, "error": 0}
    hour_totals = {"ok": 0, "no_data": 0, "rate_limited": 0, "blocked": 0, "error": 0}
    start_time = time.monotonic()
    hour_start = start_time
    request_num = 0
    asin_idx = 0

    async with AsyncSession(impersonate="chrome") as session:
        while not shutdown:
            elapsed_hours = (time.monotonic() - start_time) / 3600
            if elapsed_hours >= DURATION_HOURS:
                log("24 hours reached — stopping")
                break

            asin = ASINS[asin_idx % len(ASINS)]
            asin_idx += 1
            request_num += 1
            url = f"{BASE_URL}/{asin}/amazon-new-used.png?{QUERY}"

            try:
                resp = await session.get(url, timeout=15, allow_redirects=True)
                status = resp.status_code
                size = len(resp.content)

                if status == 200 and size > 15000:
                    totals["ok"] += 1
                    hour_totals["ok"] += 1
                elif status == 200:
                    totals["no_data"] += 1
                    hour_totals["no_data"] += 1
                elif status == 429:
                    totals["rate_limited"] += 1
                    hour_totals["rate_limited"] += 1
                    log(f"⚠️ 429 at request #{request_num} ({asin})")
                elif status == 403:
                    totals["blocked"] += 1
                    hour_totals["blocked"] += 1
                    log(f"🚫 403 BLOCKED at request #{request_num} ({asin})")
                else:
                    totals["error"] += 1
                    hour_totals["error"] += 1
                    log(f"❌ HTTP {status} at request #{request_num} ({asin})")

            except Exception as e:
                totals["error"] += 1
                hour_totals["error"] += 1
                log(f"❌ ERROR at request #{request_num}: {e}")

            # Hourly summary
            if time.monotonic() - hour_start >= 3600:
                hours_done = int(elapsed_hours) + 1
                success = hour_totals["ok"] + hour_totals["no_data"]
                problems = hour_totals["rate_limited"] + hour_totals["blocked"] + hour_totals["error"]
                log(f"📊 Hour {hours_done}: {success} ok / {problems} problems "
                    f"(429:{hour_totals['rate_limited']} 403:{hour_totals['blocked']} err:{hour_totals['error']})")
                hour_totals = {"ok": 0, "no_data": 0, "rate_limited": 0, "blocked": 0, "error": 0}
                hour_start = time.monotonic()

            await asyncio.sleep(DELAY)

    # Final report
    elapsed = time.monotonic() - start_time
    hours = elapsed / 3600
    success = totals["ok"] + totals["no_data"]
    problems = totals["rate_limited"] + totals["blocked"] + totals["error"]

    log("=" * 60)
    log(f"FINAL REPORT — {hours:.1f} hours, {request_num} requests")
    log(f"  Charts:       {totals['ok']}")
    log(f"  No-data:      {totals['no_data']}")
    log(f"  Rate-limited: {totals['rate_limited']}")
    log(f"  Blocked:      {totals['blocked']}")
    log(f"  Errors:       {totals['error']}")
    log(f"  Success rate: {success}/{request_num} = {success/max(request_num,1)*100:.1f}%")
    log("=" * 60)

    # Cleanup PID file
    PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
