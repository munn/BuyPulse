"""T011: Unit tests for cps.crawler.rate_limiter — RateLimiter.

These tests verify:
- First acquire() is immediate (no wait)
- Subsequent acquire() calls are spaced by 1/rate seconds
- Rapid burst of N requests takes >= (N-1)/rate seconds
- trigger_cooldown() pauses acquire for cooldown_secs
- Custom rate parameter adjusts spacing
- Concurrent acquire() calls are serialized
"""

import asyncio
import time

import pytest

from cps.crawler.rate_limiter import RateLimiter


class TestRateLimiterBasic:
    """Basic rate limiting behavior."""

    async def test_first_request_is_immediate(self):
        """First acquire() should return with negligible delay."""
        limiter = RateLimiter(rate=1.0)

        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start

        # First request should take less than 100ms
        assert elapsed < 0.1

    async def test_subsequent_requests_spaced_by_interval(self):
        """Two sequential acquire() calls should be spaced >= 1/rate seconds."""
        limiter = RateLimiter(rate=1.0)

        await limiter.acquire()
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start

        # With rate=1.0, spacing should be >= 1.0 second
        assert elapsed >= 0.9  # Allow small timing tolerance

    async def test_five_rapid_requests_take_at_least_four_seconds(self):
        """5 rapid requests at rate=1.0 should take >= 4 seconds total."""
        limiter = RateLimiter(rate=1.0)

        start = time.monotonic()
        for _ in range(5):
            await limiter.acquire()
        elapsed = time.monotonic() - start

        # 5 requests with 1s spacing: first is free, 4 waits of ~1s each
        assert elapsed >= 3.8  # Allow timing tolerance


class TestRateLimiterCooldown:
    """Cooldown mode after HTTP 429."""

    async def test_cooldown_pauses_for_configured_duration(self):
        """After trigger_cooldown(), next acquire() waits for cooldown_secs."""
        cooldown_secs = 2.0
        limiter = RateLimiter(rate=1.0, cooldown_secs=cooldown_secs)

        # First request (immediate)
        await limiter.acquire()

        # Trigger cooldown (simulating a 429 response)
        limiter.trigger_cooldown()

        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start

        # Should wait at least the cooldown duration
        assert elapsed >= cooldown_secs - 0.2  # Tolerance for timer precision


class TestRateLimiterConfigurable:
    """Rate parameter controls spacing."""

    async def test_rate_2_means_half_second_spacing(self):
        """rate=2.0 means 2 requests/sec, so 0.5s spacing."""
        limiter = RateLimiter(rate=2.0)

        await limiter.acquire()
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start

        # With rate=2.0, spacing should be ~0.5s
        assert elapsed >= 0.4  # Tolerance
        assert elapsed < 1.0  # Should be much less than 1s

    async def test_rate_10_means_100ms_spacing(self):
        """rate=10.0 means 10 requests/sec, so 0.1s spacing."""
        limiter = RateLimiter(rate=10.0)

        await limiter.acquire()
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start

        assert elapsed >= 0.08  # ~100ms with tolerance
        assert elapsed < 0.3


class TestRateLimiterConcurrency:
    """Concurrent acquire() calls must be serialized."""

    async def test_concurrent_acquires_are_serialized(self):
        """Multiple concurrent acquire() calls should not bypass rate limit."""
        limiter = RateLimiter(rate=2.0)  # 0.5s spacing

        timestamps: list[float] = []

        async def timed_acquire():
            await limiter.acquire()
            timestamps.append(time.monotonic())

        # Launch 4 concurrent acquire tasks
        start = time.monotonic()
        tasks = [asyncio.create_task(timed_acquire()) for _ in range(4)]
        await asyncio.gather(*tasks)
        total_elapsed = time.monotonic() - start

        # 4 requests at rate=2.0: first immediate, then 3 waits of 0.5s
        # Total should be >= 1.5s (3 * 0.5s)
        assert total_elapsed >= 1.3  # Tolerance

        # Check that timestamps are properly spaced
        timestamps.sort()
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i - 1]
            assert gap >= 0.4  # Each pair should be ~0.5s apart
