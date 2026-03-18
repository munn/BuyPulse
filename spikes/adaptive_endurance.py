"""Adaptive 24h endurance test: auto-adjusts rate to find maximum sustainable throughput.

Strategy:
- Start at 1.0 req/s (1.0s delay)
- On 429: back off (double delay, min 2s, max 300s cooldown pause)
- On 3 consecutive 429s: long cooldown (120-300s), then resume slower
- On sustained success (100+ consecutive OK): try speeding up (reduce delay by 10%)
- Track hourly and cumulative stats
- Find optimal sustainable rate over 24 hours

Run:   nohup uv run python spikes/adaptive_endurance.py &
Check: tail -f spikes/adaptive_log.txt
Stop:  kill $(cat spikes/adaptive.pid)
"""

import asyncio
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi.requests import AsyncSession

BASE_URL = "https://charts.camelcamelcamel.com/us"
QUERY = "force=1&zero=0&w=855&h=513&desired=false&legend=1&ilt=1&tp=all&fo=0&lang=en"
DURATION_HOURS = 24

LOG_FILE = Path("spikes/adaptive_log.txt")
PID_FILE = Path("spikes/adaptive.pid")
STATS_FILE = Path("spikes/adaptive_stats.json")

# Adaptive parameters
INITIAL_DELAY = 1.0        # Start at 1 req/s
MIN_DELAY = 0.5            # Never go faster than 2 req/s
MAX_DELAY = 5.0            # Never go slower than 0.2 req/s
SPEEDUP_THRESHOLD = 100    # Speed up after N consecutive successes
SPEEDUP_FACTOR = 0.90      # Reduce delay by 10% on speedup
SLOWDOWN_FACTOR = 2.0      # Double delay on 429
COOLDOWN_TRIGGER = 3       # Consecutive 429s before long cooldown
COOLDOWN_SHORT = 60        # Short cooldown seconds
COOLDOWN_LONG = 180        # Long cooldown seconds
COOLDOWN_ESCALATE = 300    # Escalated cooldown if repeated

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


def save_stats(stats: dict):
    """Persist stats to JSON for external inspection."""
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, default=str)


async def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    PID_FILE.write_text(str(os.getpid()))

    log(f"Adaptive endurance test started — PID {os.getpid()}")
    log(f"Target: {DURATION_HOURS}h, initial rate: {1/INITIAL_DELAY:.1f} req/s")
    log(f"Strategy: auto-backoff on 429, auto-speedup after {SPEEDUP_THRESHOLD} consecutive OKs")
    log(f"Stop: kill $(cat {PID_FILE})")

    # State
    delay = INITIAL_DELAY
    consecutive_ok = 0
    consecutive_429 = 0
    cooldown_count = 0  # How many cooldowns we've done total
    request_num = 0
    asin_idx = 0

    start_time = time.monotonic()
    hour_start = start_time

    # Cumulative stats
    totals = {"ok": 0, "no_data": 0, "rate_limited": 0, "blocked": 0, "error": 0}
    hour_totals = {"ok": 0, "no_data": 0, "rate_limited": 0, "blocked": 0, "error": 0}

    # Tracking for analysis
    hourly_reports = []
    rate_history = []  # [(elapsed_secs, delay, event)]
    best_sustained_rate = INITIAL_DELAY  # Best delay that lasted 100+ requests

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
                    consecutive_ok += 1
                    consecutive_429 = 0

                    # Auto-speedup after sustained success
                    if consecutive_ok >= SPEEDUP_THRESHOLD and delay > MIN_DELAY:
                        old_delay = delay
                        delay = max(MIN_DELAY, delay * SPEEDUP_FACTOR)
                        consecutive_ok = 0
                        rate_history.append((
                            time.monotonic() - start_time,
                            delay,
                            f"speedup {old_delay:.2f}→{delay:.2f}s"
                        ))
                        log(f"⚡ Speedup: {old_delay:.2f}s → {delay:.2f}s "
                            f"({1/delay:.2f} req/s) after {SPEEDUP_THRESHOLD} consecutive OKs")

                    # Track best sustained rate
                    if consecutive_ok >= SPEEDUP_THRESHOLD and delay < best_sustained_rate:
                        best_sustained_rate = delay

                elif status == 200:
                    totals["no_data"] += 1
                    hour_totals["no_data"] += 1
                    consecutive_ok += 1
                    consecutive_429 = 0

                elif status == 429:
                    totals["rate_limited"] += 1
                    hour_totals["rate_limited"] += 1
                    consecutive_ok = 0
                    consecutive_429 += 1

                    if consecutive_429 >= COOLDOWN_TRIGGER:
                        # Long cooldown
                        cooldown_count += 1
                        if cooldown_count <= 2:
                            cooldown_secs = COOLDOWN_LONG
                        else:
                            cooldown_secs = COOLDOWN_ESCALATE

                        old_delay = delay
                        delay = min(MAX_DELAY, delay * SLOWDOWN_FACTOR)
                        consecutive_429 = 0

                        rate_history.append((
                            time.monotonic() - start_time,
                            delay,
                            f"cooldown #{cooldown_count}: {cooldown_secs}s pause, "
                            f"rate {old_delay:.2f}→{delay:.2f}s"
                        ))
                        log(f"🧊 Cooldown #{cooldown_count}: pausing {cooldown_secs}s, "
                            f"rate {old_delay:.2f}s → {delay:.2f}s ({1/delay:.2f} req/s)")

                        await asyncio.sleep(cooldown_secs)
                        continue  # Skip the normal delay

                    else:
                        # Quick backoff — just slow down
                        old_delay = delay
                        delay = min(MAX_DELAY, delay * 1.5)
                        rate_history.append((
                            time.monotonic() - start_time,
                            delay,
                            f"backoff {old_delay:.2f}→{delay:.2f}s"
                        ))
                        log(f"⚠️ 429 #{consecutive_429} at req #{request_num}: "
                            f"backoff {old_delay:.2f}s → {delay:.2f}s")

                elif status == 403:
                    totals["blocked"] += 1
                    hour_totals["blocked"] += 1
                    consecutive_ok = 0
                    log(f"🚫 403 BLOCKED at req #{request_num} ({asin})")

                else:
                    totals["error"] += 1
                    hour_totals["error"] += 1
                    consecutive_ok = 0
                    log(f"❌ HTTP {status} at req #{request_num} ({asin})")

            except Exception as e:
                totals["error"] += 1
                hour_totals["error"] += 1
                consecutive_ok = 0
                log(f"❌ ERROR at req #{request_num}: {e}")

            # Hourly summary
            if time.monotonic() - hour_start >= 3600:
                hours_done = int(elapsed_hours) + 1
                success = hour_totals["ok"] + hour_totals["no_data"]
                problems = hour_totals["rate_limited"] + hour_totals["blocked"] + hour_totals["error"]
                success_rate = success / max(success + problems, 1) * 100

                report = {
                    "hour": hours_done,
                    "ok": hour_totals["ok"],
                    "no_data": hour_totals["no_data"],
                    "rate_limited": hour_totals["rate_limited"],
                    "blocked": hour_totals["blocked"],
                    "error": hour_totals["error"],
                    "success_rate": round(success_rate, 1),
                    "current_delay": round(delay, 3),
                    "current_rate": round(1 / delay, 2),
                    "cooldowns": cooldown_count,
                }
                hourly_reports.append(report)

                log(f"📊 Hour {hours_done}: {success} ok / {problems} problems "
                    f"({success_rate:.1f}% success) | rate: {1/delay:.2f} req/s | "
                    f"cooldowns so far: {cooldown_count}")

                # Reset hourly
                hour_totals = {"ok": 0, "no_data": 0, "rate_limited": 0, "blocked": 0, "error": 0}
                hour_start = time.monotonic()

                # Persist stats every hour
                save_stats({
                    "status": "running",
                    "hours_elapsed": hours_done,
                    "current_delay_s": round(delay, 3),
                    "current_rate_rps": round(1 / delay, 2),
                    "total_requests": request_num,
                    "totals": totals,
                    "cooldown_count": cooldown_count,
                    "best_sustained_delay_s": round(best_sustained_rate, 3),
                    "hourly_reports": hourly_reports,
                    "rate_changes": [
                        {"elapsed_s": round(t, 1), "delay_s": round(d, 3), "event": e}
                        for t, d, e in rate_history[-50:]  # Last 50 changes
                    ],
                })

            await asyncio.sleep(delay)

    # ── Final report ──────────────────────────────────────────────
    elapsed = time.monotonic() - start_time
    hours = elapsed / 3600
    total_success = totals["ok"] + totals["no_data"]
    total_problems = totals["rate_limited"] + totals["blocked"] + totals["error"]
    overall_rate = total_success / max(total_success + total_problems, 1) * 100
    effective_rps = request_num / max(elapsed, 1)

    log("=" * 70)
    log(f"FINAL REPORT — {hours:.1f} hours, {request_num} requests")
    log(f"  Charts OK:       {totals['ok']}")
    log(f"  No-data:         {totals['no_data']}")
    log(f"  Rate-limited:    {totals['rate_limited']}")
    log(f"  Blocked:         {totals['blocked']}")
    log(f"  Errors:          {totals['error']}")
    log(f"  Success rate:    {overall_rate:.1f}%")
    log(f"  Effective rate:  {effective_rps:.3f} req/s (including cooldowns)")
    log(f"  Total cooldowns: {cooldown_count}")
    log(f"  Final delay:     {delay:.3f}s ({1/delay:.2f} req/s)")
    log(f"  Best sustained:  {best_sustained_rate:.3f}s ({1/best_sustained_rate:.2f} req/s)")
    log("")
    log("HOURLY BREAKDOWN:")
    for r in hourly_reports:
        log(f"  Hour {r['hour']:2d}: {r['ok']:4d} ok, {r['rate_limited']:3d} 429s, "
            f"{r['success_rate']:5.1f}% | {r['current_rate']:.2f} req/s")
    log("")
    log("RECOMMENDED PRODUCTION SETTINGS:")
    safe_delay = max(best_sustained_rate * 1.2, 1.0)  # 20% safety margin
    log(f"  Safe delay:      {safe_delay:.2f}s ({1/safe_delay:.2f} req/s)")
    log(f"  Daily capacity:  ~{int(86400 / safe_delay):,} requests/day")
    log(f"  With 2 IPs:      ~{int(86400 / safe_delay * 2):,} requests/day")
    log("=" * 70)

    # Final stats save
    save_stats({
        "status": "completed",
        "hours_elapsed": round(hours, 1),
        "total_requests": request_num,
        "totals": totals,
        "overall_success_rate": round(overall_rate, 1),
        "effective_rps": round(effective_rps, 3),
        "cooldown_count": cooldown_count,
        "final_delay_s": round(delay, 3),
        "best_sustained_delay_s": round(best_sustained_rate, 3),
        "recommended_safe_delay_s": round(safe_delay, 2),
        "recommended_daily_capacity": int(86400 / safe_delay),
        "hourly_reports": hourly_reports,
        "rate_changes": [
            {"elapsed_s": round(t, 1), "delay_s": round(d, 3), "event": e}
            for t, d, e in rate_history
        ],
    })

    PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
