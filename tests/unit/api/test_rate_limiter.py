"""Tests for login brute-force rate limiter."""

import time

from cps.api.auth import LoginRateLimiter


class TestLoginRateLimiter:
    def test_allows_first_attempt(self):
        limiter = LoginRateLimiter(max_attempts=10, window_seconds=300, lockout_seconds=900)
        assert limiter.is_allowed("1.2.3.4") is True

    def test_allows_up_to_max_attempts(self):
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=300, lockout_seconds=900)
        for _ in range(3):
            limiter.record_attempt("1.2.3.4")
        assert limiter.is_allowed("1.2.3.4") is True

    def test_blocks_after_max_attempts(self):
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=300, lockout_seconds=900)
        for _ in range(4):
            limiter.record_attempt("1.2.3.4")
        assert limiter.is_allowed("1.2.3.4") is False

    def test_different_ips_independent(self):
        limiter = LoginRateLimiter(max_attempts=2, window_seconds=300, lockout_seconds=900)
        for _ in range(3):
            limiter.record_attempt("1.1.1.1")
        assert limiter.is_allowed("1.1.1.1") is False
        assert limiter.is_allowed("2.2.2.2") is True

    def test_lockout_expires(self):
        limiter = LoginRateLimiter(max_attempts=2, window_seconds=300, lockout_seconds=1)
        for _ in range(3):
            limiter.record_attempt("1.2.3.4")
        assert limiter.is_allowed("1.2.3.4") is False
        time.sleep(1.1)
        assert limiter.is_allowed("1.2.3.4") is True

    def test_record_resets_on_success(self):
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=300, lockout_seconds=900)
        for _ in range(2):
            limiter.record_attempt("1.2.3.4")
        limiter.record_success("1.2.3.4")
        assert limiter.is_allowed("1.2.3.4") is True
