"""Authentication service — password hashing and session management."""

import secrets
import time as _time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import AdminSession, AdminUser


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


async def create_session(db: AsyncSession, user_id: int, ttl_days: int) -> str:
    """Create a new admin session, returning the session token."""
    # Clean up expired sessions for this user
    await db.execute(
        delete(AdminSession).where(
            AdminSession.user_id == user_id,
            AdminSession.expires_at < datetime.now(timezone.utc),
        )
    )
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    session_row = AdminSession(
        user_id=user_id, session_token=token, expires_at=expires_at,
    )
    db.add(session_row)
    await db.flush()
    return token


async def validate_session(db: AsyncSession, token: str) -> AdminUser | None:
    """Validate a session token. Returns the user if valid, None otherwise."""
    result = await db.execute(
        select(AdminSession).where(AdminSession.session_token == token)
    )
    session_row = result.scalar_one_or_none()
    if session_row is None:
        return None

    if session_row.expires_at < datetime.now(timezone.utc):
        await db.execute(delete(AdminSession).where(AdminSession.id == session_row.id))
        await db.flush()
        return None

    user_result = await db.execute(
        select(AdminUser).where(
            AdminUser.id == session_row.user_id,
            AdminUser.is_active == True,  # noqa: E712
        )
    )
    return user_result.scalar_one_or_none()


async def delete_session(db: AsyncSession, token: str) -> None:
    """Delete a session by token (logout)."""
    await db.execute(delete(AdminSession).where(AdminSession.session_token == token))
    await db.flush()


@dataclass
class _IpRecord:
    attempts: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class LoginRateLimiter:
    """In-memory brute-force protection for login attempts."""

    def __init__(self, max_attempts: int = 10, window_seconds: int = 300, lockout_seconds: int = 900) -> None:
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._records: dict[str, _IpRecord] = defaultdict(_IpRecord)

    def is_allowed(self, ip: str) -> bool:
        record = self._records[ip]
        now = _time.monotonic()
        if record.locked_until > now:
            return False
        # Lockout just expired — clear the slate so the IP can retry
        if record.locked_until > 0:
            record.locked_until = 0.0
            record.attempts = []
            return True
        cutoff = now - self._window
        record.attempts = [t for t in record.attempts if t > cutoff]
        return len(record.attempts) < self._max_attempts

    def record_attempt(self, ip: str) -> None:
        record = self._records[ip]
        now = _time.monotonic()
        record.attempts.append(now)
        cutoff = now - self._window
        recent = [t for t in record.attempts if t > cutoff]
        if len(recent) > self._max_attempts:
            record.locked_until = now + self._lockout

    def record_success(self, ip: str) -> None:
        if ip in self._records:
            del self._records[ip]
