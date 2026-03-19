"""Tests for crawl interval lookup by priority tier."""

from datetime import timedelta

import pytest


class TestGetCrawlInterval:
    """Spec Section 4.1 — priority-based crawl intervals."""

    @pytest.mark.parametrize("priority,expected_hours", [
        (1, 24), (2, 24), (3, 24),
    ])
    def test_high_priority_daily(self, priority, expected_hours):
        from cps.scheduler.intervals import get_crawl_interval
        assert get_crawl_interval(priority) == timedelta(hours=expected_hours)

    @pytest.mark.parametrize("priority,expected_days", [
        (4, 7), (5, 7), (6, 7),
    ])
    def test_medium_priority_weekly(self, priority, expected_days):
        from cps.scheduler.intervals import get_crawl_interval
        assert get_crawl_interval(priority) == timedelta(days=expected_days)

    @pytest.mark.parametrize("priority,expected_days", [
        (7, 30), (8, 30), (9, 30), (10, 30),
    ])
    def test_low_priority_monthly(self, priority, expected_days):
        from cps.scheduler.intervals import get_crawl_interval
        assert get_crawl_interval(priority) == timedelta(days=expected_days)

    @pytest.mark.parametrize("priority", [0, -1, 11, 99])
    def test_out_of_range_falls_back_to_weekly(self, priority):
        from cps.scheduler.intervals import get_crawl_interval
        assert get_crawl_interval(priority) == timedelta(days=7)
