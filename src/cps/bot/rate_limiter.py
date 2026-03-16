"""Per-user rate limiting (spec Section 7.2).

| Limit                         | Value | Purpose                |
|-------------------------------|-------|------------------------|
| Messages per minute per user  | 10    | Prevent spam/abuse     |
| Price queries per day per user| 50    | Control AI API cost    |
"""
from enum import Enum

_MSG_PER_MINUTE = 10
_QUERIES_PER_DAY = 50
_MINUTE = 60.0
_DAY = 86400.0


class RateLimitResult(str, Enum):
    ALLOWED = "allowed"
    MSG_RATE_EXCEEDED = "msg_rate_exceeded"
    DAILY_LIMIT_EXCEEDED = "daily_limit_exceeded"


def check_rate_limit(state: dict, user_id: int, now: float) -> RateLimitResult:
    """Check and update rate limit state. Pure function with external state dict.

    state format: {user_id: {"minute_timestamps": [...], "day_start": float, "day_count": int}}
    """
    if user_id not in state:
        state[user_id] = {"minute_timestamps": [], "day_start": now, "day_count": 0}

    user_state = state[user_id]

    # Clean old minute timestamps
    cutoff = now - _MINUTE
    user_state["minute_timestamps"] = [
        ts for ts in user_state["minute_timestamps"] if ts > cutoff
    ]

    # Check msg/min
    if len(user_state["minute_timestamps"]) >= _MSG_PER_MINUTE:
        return RateLimitResult.MSG_RATE_EXCEEDED

    # Reset daily counter if day passed
    if now - user_state["day_start"] > _DAY:
        user_state["day_start"] = now
        user_state["day_count"] = 0

    # Check daily limit
    if user_state["day_count"] >= _QUERIES_PER_DAY:
        return RateLimitResult.DAILY_LIMIT_EXCEEDED

    # Allow and record
    user_state["minute_timestamps"].append(now)
    user_state["day_count"] += 1
    return RateLimitResult.ALLOWED
