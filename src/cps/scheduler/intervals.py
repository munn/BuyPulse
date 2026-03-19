"""Crawl interval constants — maps priority tiers to re-crawl frequency.

Spec Section 4: Priority-Based Crawl Intervals.
"""

from datetime import timedelta

import structlog

log = structlog.get_logger()

_INTERVALS: list[tuple[range, timedelta]] = [
    (range(1, 4), timedelta(hours=24)),    # P1-3: High — daily
    (range(4, 7), timedelta(days=7)),      # P4-6: Medium — weekly
    (range(7, 11), timedelta(days=30)),    # P7-10: Low — monthly
]

_FALLBACK = timedelta(days=7)


def get_crawl_interval(priority: int) -> timedelta:
    """Return the crawl interval for a given priority.

    Valid priorities: 1-10. Out-of-range values fall back to 7 days with a warning.
    """
    for priority_range, interval in _INTERVALS:
        if priority in priority_range:
            return interval
    log.warning("priority_out_of_range", priority=priority, fallback_days=7)
    return _FALLBACK
