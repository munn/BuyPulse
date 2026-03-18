"""Auth routes — login, logout, current user."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.auth import LoginRateLimiter, create_session, verify_password
from cps.api.auth import delete_session as delete_session_fn
from cps.api.deps import get_current_user, get_db, log_audit
from cps.api.schemas.auth import LoginRequest, UserResponse
from cps.api.schemas.locale import LocaleUpdateRequest
from cps.config import get_settings
from cps.db.models import AdminUser

router = APIRouter(prefix="/auth", tags=["auth"])
_rate_limiter = LoginRateLimiter(max_attempts=10, window_seconds=300, lockout_seconds=900)


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response,
                db: Annotated[AsyncSession, Depends(get_db)]):
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts")

    result = await db.execute(
        select(AdminUser).where(AdminUser.username == body.username, AdminUser.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        _rate_limiter.record_attempt(client_ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _rate_limiter.record_success(client_ip)
    settings = get_settings()
    token = await create_session(db, user.id, settings.session_ttl_days)
    await db.commit()

    response.set_cookie(
        key="cps_session", value=token, httponly=True, samesite="lax",
        path="/api", secure=not settings.debug, max_age=settings.session_ttl_days * 86400,
    )
    await log_audit(db, user.id, "login", "session", client_ip)
    await db.commit()
    return UserResponse.model_validate(user)


@router.post("/logout")
async def logout(request: Request, response: Response,
                 db: Annotated[AsyncSession, Depends(get_db)],
                 current_user: Annotated[AdminUser, Depends(get_current_user)]):
    token = request.cookies.get("cps_session")
    if token:
        await delete_session_fn(db, token)
    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, current_user.id, "logout", "session", client_ip)
    await db.commit()
    response.delete_cookie(key="cps_session", path="/api")
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: Annotated[AdminUser, Depends(get_current_user)]):
    return UserResponse.model_validate(current_user)


@router.patch("/locale")
async def update_locale(
    body: LocaleUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    current_user.locale = body.locale
    await db.commit()
    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, current_user.id, "update_locale", "user", client_ip, str(current_user.id))
    return {"locale": current_user.locale}
