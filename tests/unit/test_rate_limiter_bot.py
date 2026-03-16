"""Tests for per-user rate limiting (spec Section 7.2)."""
import time

from cps.bot.rate_limiter import RateLimitResult, check_rate_limit


class TestRateLimit:
    def test_first_message_allowed(self):
        state: dict = {}
        result = check_rate_limit(state, user_id=1, now=time.time())
        assert result == RateLimitResult.ALLOWED

    def test_11th_message_in_one_minute_blocked(self):
        state: dict = {}
        now = time.time()
        for _ in range(10):
            check_rate_limit(state, user_id=1, now=now)
        result = check_rate_limit(state, user_id=1, now=now + 0.1)
        assert result == RateLimitResult.MSG_RATE_EXCEEDED

    def test_messages_allowed_after_minute_passes(self):
        state: dict = {}
        now = time.time()
        for _ in range(10):
            check_rate_limit(state, user_id=1, now=now)
        result = check_rate_limit(state, user_id=1, now=now + 61)
        assert result == RateLimitResult.ALLOWED

    def test_51st_query_per_day_blocked(self):
        state: dict = {}
        now = time.time()
        for i in range(50):
            # Space messages 7 seconds apart to avoid msg/min limit
            check_rate_limit(state, user_id=1, now=now + i * 7)
        result = check_rate_limit(state, user_id=1, now=now + 50 * 7)
        assert result == RateLimitResult.DAILY_LIMIT_EXCEEDED

    def test_different_users_independent(self):
        state: dict = {}
        now = time.time()
        for _ in range(10):
            check_rate_limit(state, user_id=1, now=now)
        result = check_rate_limit(state, user_id=2, now=now)
        assert result == RateLimitResult.ALLOWED
