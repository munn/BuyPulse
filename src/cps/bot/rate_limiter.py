"""Per-user rate limiting — stub for Chunk 5, full implementation in T20."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    reason: str = ""


async def check_rate_limit(user_id: int) -> RateLimitResult:
    """Check if user is within rate limits. Stub: always allows."""
    return RateLimitResult(allowed=True)
