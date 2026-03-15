"""Token-bucket rate limiter with cooldown support for HTTP 429 handling."""

import asyncio
import time


class RateLimiter:
    """Enforces a maximum request rate with optional cooldown after 429 responses.

    Uses a token-bucket approach: tracks the timestamp of the last allowed request
    and sleeps as needed to maintain the configured interval between requests.
    An asyncio.Lock serializes concurrent callers.
    """

    def __init__(self, rate: float = 1.0, cooldown_secs: float = 60.0) -> None:
        """Initialize the rate limiter.

        Args:
            rate: Maximum requests per second. Interval = 1/rate seconds.
            cooldown_secs: Duration to pause after a 429 response.
        """
        self._interval = 1.0 / rate
        self._cooldown_secs = cooldown_secs
        self._lock = asyncio.Lock()
        self._last_request_time: float | None = None
        self._cooldown_until: float | None = None

    async def acquire(self) -> None:
        """Wait until it is safe to make the next request.

        The first call returns immediately. Subsequent calls sleep to
        enforce the configured interval. If a cooldown is active, waits
        for the cooldown duration before proceeding.
        """
        async with self._lock:
            now = time.monotonic()

            # Handle cooldown mode (triggered by 429)
            if self._cooldown_until is not None:
                wait = self._cooldown_until - now
                if wait > 0:
                    await asyncio.sleep(wait)
                self._cooldown_until = None
                self._last_request_time = time.monotonic()
                return

            # First request is immediate
            if self._last_request_time is None:
                self._last_request_time = now
                return

            # Enforce interval between requests
            elapsed = now - self._last_request_time
            wait = self._interval - elapsed
            if wait > 0:
                await asyncio.sleep(wait)

            self._last_request_time = time.monotonic()

    def trigger_cooldown(self) -> None:
        """Enter cooldown mode so the next acquire() waits cooldown_secs.

        Call this after receiving an HTTP 429 response.
        """
        self._cooldown_until = time.monotonic() + self._cooldown_secs
