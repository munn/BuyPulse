"""FastAPI dependency injection — DB session and current user."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.auth import validate_session
from cps.db.models import AdminUser, AuditLog


_session_factory = None


async def get_db():
    """Yield a database session."""
    global _session_factory
    if _session_factory is None:
        from cps.config import get_settings
        from cps.db.session import create_session_factory
        settings = get_settings()
        _session_factory = create_session_factory(settings.database_url)
    async with _session_factory() as session:
        yield session


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    cps_session: str | None = Cookie(default=None),
) -> AdminUser:
    """Extract and validate the current admin user from session cookie."""
    if cps_session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await validate_session(db, cps_session)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return user


async def log_audit(
    db: AsyncSession, user_id: int, action: str, resource_type: str,
    ip_address: str, resource_id: str | None = None, details: dict | None = None,
) -> None:
    """Record an audit log entry."""
    entry = AuditLog(
        user_id=user_id, action=action, resource_type=resource_type,
        resource_id=resource_id, details=details, ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()
