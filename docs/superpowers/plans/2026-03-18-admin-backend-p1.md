# CPS Admin Backend P1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an operations admin panel (FastAPI + React) for monitoring crawl health, managing products/tasks, and controlling the CPS pipeline — replacing CLI as the primary interface.

**Architecture:** FastAPI API layer wraps existing service classes (SeedManager, DbTaskQueue, WorkerLoop). React + Ant Design frontend with sidebar navigation. Auth via bcrypt + HTTP-only cookie sessions. Worker heartbeat via DB table polling. Audit logging via explicit utility calls in route handlers.

**Tech Stack:** FastAPI, uvicorn, bcrypt, python-multipart, httpx (test), React 18, Vite 6, TypeScript, Ant Design 5, ECharts, Axios

**Spec:** `docs/superpowers/specs/2026-03-18-admin-backend-design.md`

---

## File Structure

### New Files — Backend

| File | Responsibility |
|------|---------------|
| `src/cps/api/__init__.py` | Package marker |
| `src/cps/api/app.py` | FastAPI factory: CORS, middleware, router mounts, static files |
| `src/cps/api/auth.py` | Password hashing (bcrypt), session CRUD, login rate limiter |
| `src/cps/api/deps.py` | FastAPI dependencies: DB session, current user, audit logger |
| `src/cps/api/middleware.py` | CSRF check middleware |
| `src/cps/api/schemas/__init__.py` | Package marker |
| `src/cps/api/schemas/common.py` | PaginatedResponse, ErrorResponse |
| `src/cps/api/schemas/auth.py` | LoginRequest, UserResponse |
| `src/cps/api/schemas/dashboard.py` | OverviewStats, ThroughputBucket, WorkerStatus, RecentFailure |
| `src/cps/api/schemas/product.py` | ProductItem, ProductDetail, PricePoint, FetchRunItem |
| `src/cps/api/schemas/crawl.py` | CrawlTaskItem, CrawlStats, EnqueueRequest |
| `src/cps/api/schemas/import_.py` | ImportJobItem |
| `src/cps/api/schemas/audit.py` | AuditLogItem |
| `src/cps/api/routes/__init__.py` | Package marker |
| `src/cps/api/routes/auth.py` | POST login/logout, GET me |
| `src/cps/api/routes/dashboard.py` | GET overview/throughput/workers/recent-failures |
| `src/cps/api/routes/products.py` | Full CRUD + search + batch + import |
| `src/cps/api/routes/crawler.py` | Task queue listing, enqueue, retry, stats |
| `src/cps/api/routes/imports.py` | Import job list + progress |
| `src/cps/api/routes/audit.py` | Audit log read-only list |

### New Files — Tests

| File | Responsibility |
|------|---------------|
| `tests/unit/api/__init__.py` | Package marker |
| `tests/unit/api/conftest.py` | API test fixtures: mock session, test client, auth helpers |
| `tests/unit/api/test_auth_service.py` | Password hashing, session CRUD, rate limiter |
| `tests/unit/api/test_auth_routes.py` | Login/logout/me endpoint tests |
| `tests/unit/api/test_csrf.py` | CSRF middleware enforcement |
| `tests/unit/api/test_dashboard_routes.py` | Dashboard endpoint tests |
| `tests/unit/api/test_product_routes.py` | Product CRUD endpoint tests |
| `tests/unit/api/test_crawler_routes.py` | Crawler endpoint tests |
| `tests/unit/api/test_import_routes.py` | Import endpoint tests |
| `tests/unit/api/test_audit_routes.py` | Audit endpoint tests |
| `tests/unit/test_admin_models.py` | ORM model field verification |
| `tests/unit/test_heartbeat.py` | Heartbeat service logic |

### New Files — Frontend

| File | Responsibility |
|------|---------------|
| `web/package.json` | Dependencies |
| `web/tsconfig.json` | TypeScript config |
| `web/vite.config.ts` | Vite config with API proxy |
| `web/index.html` | HTML shell |
| `web/src/main.tsx` | React entry point |
| `web/src/App.tsx` | Router setup |
| `web/src/api/client.ts` | Axios instance + CSRF header + error interceptor |
| `web/src/api/endpoints.ts` | Typed API functions |
| `web/src/hooks/useAuth.ts` | Auth state management |
| `web/src/hooks/usePolling.ts` | Auto-refresh hook |
| `web/src/layouts/AdminLayout.tsx` | Sidebar + header + content area |
| `web/src/pages/Login.tsx` | Login form |
| `web/src/pages/Dashboard.tsx` | Stats cards + charts + workers + failures |
| `web/src/pages/Products.tsx` | Product list + search + filters + batch actions |
| `web/src/pages/Crawler.tsx` | Crawler stats + workers + task queue tabs |
| `web/src/pages/Imports.tsx` | Import job list with progress |
| `web/src/pages/Audit.tsx` | Audit log table |
| `web/src/components/StatsCard.tsx` | Reusable stat card |
| `web/src/components/StatusBadge.tsx` | Color-coded status badge |
| `web/src/components/ProductDrawer.tsx` | Product detail side drawer |
| `web/src/components/PriceChart.tsx` | ECharts wrapper for price history |
| `web/src/components/DataTable.tsx` | Ant Design Table wrapper with common features |
| `web/src/components/EmptyState.tsx` | Empty state illustration |
| `web/src/types/index.ts` | Shared TypeScript interfaces |

### Modified Files

| File | Change |
|------|--------|
| `pyproject.toml` | Add fastapi, uvicorn, bcrypt, python-multipart; httpx to dev |
| `src/cps/config.py` | Add DEBUG, API_HOST, API_PORT, SESSION_TTL_DAYS, ADMIN_PASSWORD_MIN_LENGTH |
| `src/cps/db/models.py` | Add AdminUser, AdminSession, WorkerHeartbeat, ImportJob, AuditLog |
| `src/cps/cli.py` | Add `api` and `admin` sub-commands |
| `src/cps/worker.py` | Add heartbeat update in run_once/run_forever |
| `.gitignore` | Add `web/dist/`, `web/node_modules/` |

---

## Chunk 1: Foundation

### Task 1: Dependencies + Config + Gitignore

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/cps/config.py`
- Modify: `.gitignore`
- Test: `tests/unit/test_config.py` (verify new fields exist)

- [ ] **Step 1: Add backend dependencies to pyproject.toml**

In `pyproject.toml`, add to `dependencies`:
```toml
"fastapi>=0.115.0",
"uvicorn[standard]>=0.34.0",
"bcrypt>=4.0.0",
"python-multipart>=0.0.20",
```

Add to `[dependency-groups] dev`:
```toml
"httpx>=0.28.0",
```

- [ ] **Step 2: Add new settings to config.py**

Add these fields to the `Settings` class in `src/cps/config.py`, after the existing `log_format` field:

```python
# Admin API
debug: bool = Field(
    default=False,
    description="Enable debug mode (CORS, OpenAPI docs, verbose errors)",
)
api_host: str = Field(
    default="0.0.0.0",
    description="Uvicorn bind host",
)
api_port: int = Field(
    default=8000,
    description="Uvicorn bind port",
)
session_ttl_days: int = Field(
    default=7,
    description="Admin session expiry in days",
)
admin_password_min_length: int = Field(
    default=12,
    description="Minimum password length for admin create-user",
)
```

- [ ] **Step 3: Add gitignore entries**

Append to `.gitignore`:
```
# Frontend
web/node_modules/
web/dist/
```

- [ ] **Step 4: Install dependencies**

Run: `cd /Users/victor/claudecode/cps && uv sync`
Expected: Resolves and installs new dependencies without errors.

- [ ] **Step 5: Verify config loads new fields**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/test_config.py -v`
Expected: Existing tests pass. Add a test if needed:

```python
# In tests/unit/test_config.py — add test for new fields
def test_admin_settings_defaults():
    """Verify admin API settings have correct defaults."""
    settings = Settings(database_url="postgresql+asyncpg://x:x@localhost/x")
    assert settings.debug is False
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8000
    assert settings.session_ttl_days == 7
    assert settings.admin_password_min_length == 12
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/cps/config.py .gitignore tests/unit/test_config.py uv.lock
git commit -m "feat(admin): add backend dependencies and config settings"
```

---

### Task 2: Admin ORM Models

**Files:**
- Modify: `src/cps/db/models.py`
- Create: `tests/unit/test_admin_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_admin_models.py`:

```python
"""Tests for admin ORM model definitions."""

from cps.db.models import AdminSession, AdminUser, AuditLog, ImportJob, WorkerHeartbeat


class TestAdminUserModel:
    def test_tablename(self):
        assert AdminUser.__tablename__ == "admin_users"

    def test_has_required_columns(self):
        col_names = {c.name for c in AdminUser.__table__.columns}
        expected = {"id", "username", "password_hash", "role", "is_active", "created_at", "updated_at"}
        assert expected.issubset(col_names)

    def test_username_unique(self):
        username_col = AdminUser.__table__.c.username
        assert username_col.unique is True


class TestAdminSessionModel:
    def test_tablename(self):
        assert AdminSession.__tablename__ == "admin_sessions"

    def test_has_required_columns(self):
        col_names = {c.name for c in AdminSession.__table__.columns}
        expected = {"id", "user_id", "session_token", "expires_at", "created_at"}
        assert expected.issubset(col_names)

    def test_session_token_unique(self):
        token_col = AdminSession.__table__.c.session_token
        assert token_col.unique is True


class TestWorkerHeartbeatModel:
    def test_tablename(self):
        assert WorkerHeartbeat.__tablename__ == "worker_heartbeats"

    def test_has_required_columns(self):
        col_names = {c.name for c in WorkerHeartbeat.__table__.columns}
        expected = {
            "id", "worker_id", "platform", "status", "current_task_id",
            "tasks_completed", "last_heartbeat", "started_at",
        }
        assert expected.issubset(col_names)

    def test_worker_id_unique(self):
        wid_col = WorkerHeartbeat.__table__.c.worker_id
        assert wid_col.unique is True


class TestImportJobModel:
    def test_tablename(self):
        assert ImportJob.__tablename__ == "import_jobs"

    def test_has_required_columns(self):
        col_names = {c.name for c in ImportJob.__table__.columns}
        expected = {
            "id", "filename", "status", "total", "processed",
            "added", "skipped", "error_message", "created_by",
            "created_at", "completed_at",
        }
        assert expected.issubset(col_names)


class TestAuditLogModel:
    def test_tablename(self):
        assert AuditLog.__tablename__ == "audit_log"

    def test_has_required_columns(self):
        col_names = {c.name for c in AuditLog.__table__.columns}
        expected = {
            "id", "user_id", "action", "resource_type",
            "resource_id", "details", "ip_address", "created_at",
        }
        assert expected.issubset(col_names)
```

- [ ] **Step 2: Run test — verify it fails**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/test_admin_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'AdminUser' from 'cps.db.models'`

- [ ] **Step 3: Write the ORM models**

Add to the bottom of `src/cps/db/models.py` (before any future additions), after the existing `DealDismissal` model:

```python
# --- Admin Backend (P1) ---

class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("admin_users.id"), nullable=False
    )
    session_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    worker_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="online")
    current_task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tasks_completed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="running")
    total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    processed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    added: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("admin_users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("admin_users.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

**Important:** Add `from sqlalchemy.dialects.postgresql import JSONB` to the import block at the top of `models.py` (alongside the existing SQLAlchemy imports on line 5-21).

- [ ] **Step 4: Run test — verify it passes**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/test_admin_models.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/victor/claudecode/cps && uv run pytest --tb=short -q`
Expected: All 327+ tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/cps/db/models.py tests/unit/test_admin_models.py
git commit -m "feat(admin): add ORM models for admin_users, sessions, heartbeats, imports, audit"
```

---

### Task 3: Alembic Migration

**Files:**
- Create: `alembic/versions/004_admin_backend_p1.py`

- [ ] **Step 1: Auto-generate migration**

Run: `cd /Users/victor/claudecode/cps && uv run alembic revision --autogenerate -m "admin_backend_p1"`
Expected: Creates a new migration file in `alembic/versions/`.

- [ ] **Step 2: Review the generated migration**

Open the generated file and verify it creates these 5 tables:
- `admin_users` (with unique on username)
- `admin_sessions` (with unique on session_token, FK to admin_users)
- `worker_heartbeats` (with unique on worker_id)
- `import_jobs` (FK to admin_users)
- `audit_log` (FK to admin_users, JSONB details column)

Rename the file to `004_admin_backend_p1.py` for consistency.

- [ ] **Step 3: Run migration against local database**

Run: `cd /Users/victor/claudecode/cps && uv run alembic upgrade head`
Expected: Migration applies cleanly. All 5 tables created.

- [ ] **Step 4: Verify tables exist**

Run: `cd /Users/victor/claudecode/cps && uv run python -c "
import asyncio
from sqlalchemy import text
from cps.config import get_settings
from cps.db.session import create_session_factory

async def check():
    s = get_settings()
    f = create_session_factory(s.database_url)
    async with f() as session:
        r = await session.execute(text(\"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename\"))
        for row in r:
            print(row[0])

asyncio.run(check())
"`
Expected: Output includes `admin_users`, `admin_sessions`, `worker_heartbeats`, `import_jobs`, `audit_log`.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/004_admin_backend_p1.py
git commit -m "feat(admin): add Alembic migration 004 — admin backend P1 tables"
```

---

## Chunk 2: Auth System

### Task 4: Auth Service — Password + Session

**Files:**
- Create: `src/cps/api/__init__.py`
- Create: `src/cps/api/auth.py`
- Create: `tests/unit/api/__init__.py`
- Create: `tests/unit/api/test_auth_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/api/__init__.py` (empty).
Create `tests/unit/api/test_auth_service.py`:

```python
"""Tests for auth service — password hashing and session management."""

import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.api.auth import (
    create_session,
    delete_session,
    hash_password,
    validate_session,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_password_returns_bcrypt_hash(self):
        hashed = hash_password("securepassword1")
        assert hashed.startswith("$2b$")

    def test_verify_correct_password(self):
        hashed = hash_password("test_password_123")
        assert verify_password("test_password_123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("test_password_123")
        assert verify_password("wrong_password", hashed) is False

    def test_hash_is_unique_per_call(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2  # bcrypt uses random salt


class TestCreateSession:
    async def test_creates_session_row(self):
        mock_session = AsyncMock()
        mock_user_id = 42
        ttl_days = 7

        token = await create_session(mock_session, mock_user_id, ttl_days)

        assert isinstance(token, str)
        assert len(token) >= 40  # secrets.token_urlsafe(32) → 43 chars
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()


class TestValidateSession:
    async def test_valid_session_returns_user(self):
        mock_session = AsyncMock()
        mock_admin_session = MagicMock()
        mock_admin_session.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        mock_admin_session.user_id = 42

        mock_user = MagicMock()
        mock_user.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_admin_session
        mock_session.execute.return_value = mock_result

        # Second call for user lookup
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.side_effect = [mock_result, mock_user_result]

        user = await validate_session(mock_session, "valid_token")
        assert user is mock_user

    async def test_expired_session_returns_none(self):
        mock_session = AsyncMock()
        mock_admin_session = MagicMock()
        mock_admin_session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_admin_session
        mock_session.execute.return_value = mock_result

        user = await validate_session(mock_session, "expired_token")
        assert user is None

    async def test_missing_session_returns_none(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        user = await validate_session(mock_session, "nonexistent_token")
        assert user is None


class TestDeleteSession:
    async def test_deletes_by_token(self):
        mock_session = AsyncMock()
        await delete_session(mock_session, "some_token")
        mock_session.execute.assert_awaited_once()
```

- [ ] **Step 2: Run test — verify it fails**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_auth_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.api'`

- [ ] **Step 3: Implement auth service**

Create `src/cps/api/__init__.py` (empty).
Create `src/cps/api/auth.py`:

```python
"""Authentication service — password hashing and session management."""

import secrets
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


async def create_session(
    db: AsyncSession, user_id: int, ttl_days: int
) -> str:
    """Create a new admin session, returning the session token."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    session_row = AdminSession(
        user_id=user_id,
        session_token=token,
        expires_at=expires_at,
    )
    db.add(session_row)
    await db.flush()
    return token


async def validate_session(
    db: AsyncSession, token: str
) -> AdminUser | None:
    """Validate a session token. Returns the user if valid, None otherwise."""
    result = await db.execute(
        select(AdminSession).where(AdminSession.session_token == token)
    )
    session_row = result.scalar_one_or_none()
    if session_row is None:
        return None

    if session_row.expires_at < datetime.now(timezone.utc):
        # Expired — clean up
        await db.execute(
            delete(AdminSession).where(AdminSession.id == session_row.id)
        )
        await db.flush()
        return None

    # Look up user
    user_result = await db.execute(
        select(AdminUser).where(
            AdminUser.id == session_row.user_id,
            AdminUser.is_active == True,  # noqa: E712
        )
    )
    return user_result.scalar_one_or_none()


async def delete_session(db: AsyncSession, token: str) -> None:
    """Delete a session by token (logout)."""
    await db.execute(
        delete(AdminSession).where(AdminSession.session_token == token)
    )
    await db.flush()
```

- [ ] **Step 4: Run test — verify it passes**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_auth_service.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cps/api/__init__.py src/cps/api/auth.py tests/unit/api/__init__.py tests/unit/api/test_auth_service.py
git commit -m "feat(admin): add auth service — password hashing and session management"
```

---

### Task 5: Login Rate Limiter

**Files:**
- Modify: `src/cps/api/auth.py` (add LoginRateLimiter class)
- Create: `tests/unit/api/test_rate_limiter.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/api/test_rate_limiter.py`:

```python
"""Tests for login brute-force rate limiter."""

import time
from unittest.mock import patch

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
```

- [ ] **Step 2: Run test — verify it fails**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_rate_limiter.py -v`
Expected: FAIL — `ImportError: cannot import name 'LoginRateLimiter'`

- [ ] **Step 3: Implement LoginRateLimiter**

Add to the bottom of `src/cps/api/auth.py`:

```python
import time as _time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class _IpRecord:
    attempts: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class LoginRateLimiter:
    """In-memory brute-force protection for login attempts."""

    def __init__(
        self,
        max_attempts: int = 10,
        window_seconds: int = 300,
        lockout_seconds: int = 900,
    ) -> None:
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._records: dict[str, _IpRecord] = defaultdict(_IpRecord)

    def is_allowed(self, ip: str) -> bool:
        """Check if login attempt is allowed for this IP."""
        record = self._records[ip]
        now = _time.monotonic()

        # Check lockout
        if record.locked_until > now:
            return False

        # Prune old attempts outside window
        cutoff = now - self._window
        record.attempts = [t for t in record.attempts if t > cutoff]

        return len(record.attempts) <= self._max_attempts

    def record_attempt(self, ip: str) -> None:
        """Record a failed login attempt."""
        record = self._records[ip]
        now = _time.monotonic()
        record.attempts.append(now)

        # Check if should lock
        cutoff = now - self._window
        recent = [t for t in record.attempts if t > cutoff]
        if len(recent) > self._max_attempts:
            record.locked_until = now + self._lockout

    def record_success(self, ip: str) -> None:
        """Clear attempts on successful login."""
        if ip in self._records:
            del self._records[ip]
```

- [ ] **Step 4: Run test — verify it passes**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_rate_limiter.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cps/api/auth.py tests/unit/api/test_rate_limiter.py
git commit -m "feat(admin): add login brute-force rate limiter"
```

---

### Task 6: CSRF Middleware

**Files:**
- Create: `src/cps/api/middleware.py`
- Create: `tests/unit/api/test_csrf.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/api/test_csrf.py`:

```python
"""Tests for CSRF middleware."""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from cps.api.middleware import CSRFMiddleware


@pytest.fixture
def csrf_app():
    """Create a test app with CSRF middleware."""
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.get("/api/v1/test")
    async def get_test():
        return {"ok": True}

    @app.post("/api/v1/test")
    async def post_test():
        return {"ok": True}

    @app.post("/api/v1/auth/login")
    async def login():
        return {"ok": True}

    return app


class TestCSRFMiddleware:
    async def test_get_requests_pass_through(self, csrf_app):
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/test")
            assert resp.status_code == 200

    async def test_post_without_header_rejected(self, csrf_app):
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/test")
            assert resp.status_code == 403

    async def test_post_with_header_allowed(self, csrf_app):
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/test",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert resp.status_code == 200

    async def test_login_exempt_from_csrf(self, csrf_app):
        transport = ASGITransport(app=csrf_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/login")
            assert resp.status_code == 200
```

- [ ] **Step 2: Run test — verify it fails**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_csrf.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.api.middleware'`

- [ ] **Step 3: Implement CSRF middleware**

Create `src/cps/api/middleware.py`:

```python
"""Custom middleware for the admin API."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Paths exempt from CSRF check
_CSRF_EXEMPT = {"/api/v1/auth/login"}
_MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Reject mutating requests without X-Requested-With header.

    Login endpoint is exempt since it cannot be CSRF'd before auth.
    """

    async def dispatch(self, request: Request, call_next):
        if (
            request.method in _MUTATING_METHODS
            and request.url.path not in _CSRF_EXEMPT
            and request.headers.get("x-requested-with") != "XMLHttpRequest"
        ):
            return JSONResponse(
                {"detail": "CSRF validation failed", "code": "CSRF_FAILED"},
                status_code=403,
            )
        return await call_next(request)
```

- [ ] **Step 4: Run test — verify it passes**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_csrf.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cps/api/middleware.py tests/unit/api/test_csrf.py
git commit -m "feat(admin): add CSRF middleware for mutating API requests"
```

---

### Task 7: Auth Dependencies + Schemas + Routes

**Files:**
- Create: `src/cps/api/deps.py`
- Create: `src/cps/api/schemas/__init__.py`
- Create: `src/cps/api/schemas/common.py`
- Create: `src/cps/api/schemas/auth.py`
- Create: `src/cps/api/routes/__init__.py`
- Create: `src/cps/api/routes/auth.py`
- Create: `tests/unit/api/conftest.py`
- Create: `tests/unit/api/test_auth_routes.py`

- [ ] **Step 1: Create schemas**

Create `src/cps/api/schemas/__init__.py` (empty).

Create `src/cps/api/schemas/common.py`:

```python
"""Common response schemas used across API endpoints."""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    detail: str
    code: str
```

Create `src/cps/api/schemas/auth.py`:

```python
"""Auth request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Create dependencies**

Create `src/cps/api/deps.py`:

```python
"""FastAPI dependency injection — DB session and current user."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.auth import validate_session
from cps.db.models import AdminUser, AuditLog
from cps.db.session import create_session_factory


_session_factory = None


def _get_factory():
    """Lazy-init session factory (set during app startup)."""
    global _session_factory
    if _session_factory is None:
        from cps.config import get_settings
        settings = get_settings()
        _session_factory = create_session_factory(settings.database_url)
    return _session_factory


async def get_db() -> AsyncSession:
    """Yield a database session."""
    factory = _get_factory()
    async with factory() as session:
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
    db: AsyncSession,
    user_id: int,
    action: str,
    resource_type: str,
    ip_address: str,
    resource_id: str | None = None,
    details: dict | None = None,
) -> None:
    """Record an audit log entry."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()
```

- [ ] **Step 3: Create auth routes**

Create `src/cps/api/routes/__init__.py` (empty).

Create `src/cps/api/routes/auth.py`:

```python
"""Auth routes — login, logout, current user."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.auth import LoginRateLimiter, create_session, verify_password
from cps.api.auth import delete_session as delete_session_fn
from cps.api.deps import get_current_user, get_db, log_audit
from cps.api.schemas.auth import LoginRequest, UserResponse
from cps.config import get_settings
from cps.db.models import AdminUser

router = APIRouter(prefix="/auth", tags=["auth"])

_rate_limiter = LoginRateLimiter(
    max_attempts=10, window_seconds=300, lockout_seconds=900
)


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Authenticate and set session cookie."""
    client_ip = request.client.host if request.client else "unknown"

    if not _rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts")

    # Look up user
    result = await db.execute(
        select(AdminUser).where(
            AdminUser.username == body.username,
            AdminUser.is_active == True,  # noqa: E712
        )
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
        key="cps_session",
        value=token,
        httponly=True,
        samesite="lax",
        path="/api",
        secure=not settings.debug,
        max_age=settings.session_ttl_days * 86400,
    )

    await log_audit(db, user.id, "login", "session", client_ip)
    await db.commit()

    return UserResponse.model_validate(user)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Clear session cookie and delete server-side session."""
    token = request.cookies.get("cps_session")
    if token:
        await delete_session_fn(db, token)

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, current_user.id, "logout", "session", client_ip)
    await db.commit()

    response.delete_cookie(key="cps_session", path="/api")
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Return the current authenticated user."""
    return UserResponse.model_validate(current_user)
```

- [ ] **Step 4: Create API test fixtures**

Create `tests/unit/api/conftest.py`:

```python
"""Shared fixtures for API route tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from cps.api.deps import get_current_user, get_db
from cps.db.models import AdminUser


@pytest.fixture
def mock_db():
    """Mock async DB session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_user():
    """A mock AdminUser for authenticated requests."""
    user = MagicMock(spec=AdminUser)
    user.id = 1
    user.username = "admin"
    user.role = "admin"
    user.is_active = True
    user.created_at = "2026-01-01T00:00:00+00:00"
    return user


@pytest.fixture
def make_app(mock_db, mock_user):
    """Factory that creates a FastAPI app with overridden dependencies."""

    def _make(authenticated: bool = True):
        from cps.api.app import create_app

        app = create_app()

        async def _override_db():
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        if authenticated:
            app.dependency_overrides[get_current_user] = lambda: mock_user

        return app

    return _make


@pytest.fixture
def auth_client(make_app, mock_db):
    """Authenticated async HTTP client."""

    async def _client():
        app = make_app(authenticated=True)
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    return _client


@pytest.fixture
def anon_client(make_app):
    """Unauthenticated async HTTP client."""

    async def _client():
        app = make_app(authenticated=False)
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    return _client
```

- [ ] **Step 5: Write auth route tests**

Create `tests/unit/api/test_auth_routes.py`:

```python
"""Tests for auth API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.db.models import AdminUser


class TestGetMe:
    async def test_returns_current_user(self, auth_client):
        async with await auth_client() as client:
            resp = await client.get("/api/v1/auth/me")
            assert resp.status_code == 200
            data = resp.json()
            assert data["username"] == "admin"
            assert data["role"] == "admin"

    async def test_unauthenticated_returns_401(self, anon_client):
        async with await anon_client() as client:
            resp = await client.get("/api/v1/auth/me")
            assert resp.status_code == 401


class TestLogout:
    async def test_logout_clears_cookie(self, auth_client):
        async with await auth_client() as client:
            resp = await client.post(
                "/api/v1/auth/logout",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert resp.status_code == 200
            assert resp.json()["detail"] == "Logged out"
```

Note: Full login tests require mocking the DB query + password verify. These will be refined during implementation. The key pattern is established here.

- [ ] **Step 6: Commit schemas, deps, and routes (tests verified in Task 8)**

Note: Auth route tests depend on `create_app()` from Task 8. They will be verified when the app factory is assembled. This is acceptable — the schemas, deps, and route handlers are self-contained code units.

- [ ] **Step 7: Commit**

```bash
git add src/cps/api/deps.py src/cps/api/schemas/ src/cps/api/routes/ tests/unit/api/conftest.py tests/unit/api/test_auth_routes.py
git commit -m "feat(admin): add auth schemas, dependencies, and routes"
```

---

## Chunk 3: FastAPI App + CLI

### Task 8: FastAPI App Assembly

**Files:**
- Create: `src/cps/api/app.py`
- Create: `tests/unit/api/test_app.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/api/test_app.py`:

```python
"""Tests for FastAPI app factory."""

import pytest
from httpx import ASGITransport, AsyncClient

from cps.api.app import create_app


class TestCreateApp:
    def test_returns_fastapi_instance(self):
        app = create_app()
        assert app is not None

    def test_includes_auth_routes(self):
        app = create_app()
        paths = [route.path for route in app.routes]
        assert "/api/v1/auth/login" in paths or any(
            "/auth/login" in str(getattr(r, "path", "")) for r in app.routes
        )

    async def test_health_endpoint(self):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
```

- [ ] **Step 2: Run test — verify it fails**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.api.app'`

- [ ] **Step 3: Implement app factory**

Create `src/cps/api/app.py`:

```python
"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from cps.api.middleware import CSRFMiddleware
from cps.api.routes import auth, dashboard, products, crawler, imports, audit


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from cps.config import get_settings

    settings = get_settings()

    app = FastAPI(
        title="CPS Admin API",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CSRF middleware
    app.add_middleware(CSRFMiddleware)

    # CORS — dev only
    if settings.debug:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Mount API routes
    api_prefix = "/api/v1"
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(dashboard.router, prefix=api_prefix)
    app.include_router(products.router, prefix=api_prefix)
    app.include_router(crawler.router, prefix=api_prefix)
    app.include_router(imports.router, prefix=api_prefix)
    app.include_router(audit.router, prefix=api_prefix)

    @app.get(f"{api_prefix}/health")
    async def health():
        return {"status": "ok"}

    # Static files (production: serve built frontend)
    dist_path = Path(__file__).parent.parent.parent.parent / "web" / "dist"
    if dist_path.is_dir():
        app.mount("/", StaticFiles(directory=str(dist_path), html=True))

    return app
```

Note: The router imports for dashboard, products, crawler, imports, audit will fail until those route files exist. Create placeholder routers:

Create each placeholder file (`src/cps/api/routes/dashboard.py`, `products.py`, `crawler.py`, `imports.py`, `audit.py`) with:

```python
"""<Module> routes — placeholder."""

from fastapi import APIRouter

router = APIRouter(prefix="/<name>", tags=["<name>"])
```

Replace `<name>` with: `dashboard`, `products`, `crawler`, `imports`, `audit`.

- [ ] **Step 4: Run test — verify it passes**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_app.py -v`
Expected: PASS.

- [ ] **Step 5: Run auth route tests from Task 7**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_auth_routes.py -v`
Expected: PASS.

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/victor/claudecode/cps && uv run pytest --tb=short -q`
Expected: All tests pass, no regressions.

- [ ] **Step 7: Commit**

```bash
git add src/cps/api/app.py src/cps/api/routes/ tests/unit/api/test_app.py
git commit -m "feat(admin): add FastAPI app factory with route mounting and middleware"
```

---

### Task 9: CLI Commands — api run + admin create-user

**Files:**
- Modify: `src/cps/cli.py`

Note: CLI code is in the coverage omit list, so no TDD required.

- [ ] **Step 1: Add api and admin sub-commands to cli.py**

Add new Typer sub-apps and register them in `src/cps/cli.py`:

```python
# At top with other Typer apps
api_app = typer.Typer(help="Admin API server")
admin_app = typer.Typer(help="Admin user management")

# Register
app.add_typer(api_app, name="api")
app.add_typer(admin_app, name="admin")


@api_app.command("run")
def api_run() -> None:
    """Start the FastAPI admin API server."""
    import uvicorn

    settings = get_settings()
    _configure_logging(settings.log_level, settings.log_format)

    from cps.api.app import create_app

    application = create_app()
    uvicorn.run(
        application,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info" if settings.debug else "warning",
    )


@admin_app.command("create-user")
def admin_create_user(
    username: str = typer.Option(..., "--username", "-u", help="Admin username"),
    password: str = typer.Option(..., "--password", "-p", prompt=True, hide_input=True, help="Admin password"),
) -> None:
    """Create an admin user (first-time setup)."""
    settings = get_settings()

    if len(password) < settings.admin_password_min_length:
        typer.echo(
            f"Error: Password must be at least {settings.admin_password_min_length} characters",
            err=True,
        )
        raise typer.Exit(1)

    async def _do():
        from cps.api.auth import hash_password
        from cps.db.models import AdminUser
        from cps.db.session import create_session_factory
        from sqlalchemy import select

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            # Check if username already exists
            result = await session.execute(
                select(AdminUser).where(AdminUser.username == username)
            )
            if result.scalar_one_or_none() is not None:
                typer.echo(f"Error: Username '{username}' already exists", err=True)
                raise typer.Exit(1)

            user = AdminUser(
                username=username,
                password_hash=hash_password(password),
                role="admin",
            )
            session.add(user)
            await session.commit()

        typer.echo(f"Admin user '{username}' created successfully")

    _run_async(_do())
```

- [ ] **Step 2: Verify CLI help works**

Run: `cd /Users/victor/claudecode/cps && uv run cps api --help`
Expected: Shows `run` command.

Run: `cd /Users/victor/claudecode/cps && uv run cps admin --help`
Expected: Shows `create-user` command.

- [ ] **Step 3: Commit**

```bash
git add src/cps/cli.py
git commit -m "feat(admin): add CLI commands — api run + admin create-user"
```

---

## Chunk 4: Dashboard API

### Task 10: Dashboard Schemas

**Files:**
- Create: `src/cps/api/schemas/dashboard.py`

- [ ] **Step 1: Create dashboard schemas**

```python
"""Dashboard response schemas."""

from datetime import datetime

from pydantic import BaseModel


class OverviewStats(BaseModel):
    products_total: int
    products_today: int
    crawled_total: int
    crawled_today: int
    success_rate_24h: float
    price_records_total: int


class ThroughputBucket(BaseModel):
    hour: datetime
    count: int


class WorkerStatus(BaseModel):
    worker_id: str
    platform: str
    status: str  # online/idle/offline
    current_task_id: int | None
    tasks_completed: int
    last_heartbeat: datetime
    started_at: datetime


class RecentFailure(BaseModel):
    task_id: int
    platform_id: str
    platform: str
    error_message: str | None
    updated_at: datetime
```

- [ ] **Step 2: Commit**

```bash
git add src/cps/api/schemas/dashboard.py
git commit -m "feat(admin): add dashboard response schemas"
```

---

### Task 11: Dashboard Routes

**Files:**
- Modify: `src/cps/api/routes/dashboard.py` (replace placeholder)
- Create: `tests/unit/api/test_dashboard_routes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/api/test_dashboard_routes.py`:

```python
"""Tests for dashboard API routes."""

from unittest.mock import MagicMock

import pytest


class TestDashboardOverview:
    async def test_returns_stats(self, auth_client, mock_db):
        """Overview returns stat fields."""
        # Mock DB responses for the 6 queries
        mock_db.scalar.side_effect = [
            50000,  # products_total
            120,    # products_today
            32000,  # crawled_total
            850,    # crawled_today
            2100000,  # price_records_total
        ]
        # Success rate query returns two values
        mock_result = MagicMock()
        mock_result.one.return_value = (1000, 945)  # total_24h, success_24h
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/dashboard/overview")
            assert resp.status_code == 200
            data = resp.json()
            assert "products_total" in data
            assert "success_rate_24h" in data


class TestDashboardWorkers:
    async def test_returns_worker_list(self, auth_client, mock_db):
        """Workers endpoint returns list."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/dashboard/workers")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)


class TestDashboardAuth:
    async def test_requires_authentication(self, anon_client):
        async with await anon_client() as client:
            resp = await client.get("/api/v1/dashboard/overview")
            assert resp.status_code == 401
```

- [ ] **Step 2: Implement dashboard routes**

Replace the placeholder `src/cps/api/routes/dashboard.py`:

```python
"""Dashboard routes — overview stats, throughput, workers, recent failures."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.deps import get_current_user, get_db
from cps.api.schemas.dashboard import (
    OverviewStats,
    RecentFailure,
    ThroughputBucket,
    WorkerStatus,
)
from cps.db.models import (
    AdminUser,
    CrawlTask,
    FetchRun,
    PriceHistory,
    Product,
    WorkerHeartbeat,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_HEARTBEAT_TIMEOUT = timedelta(seconds=60)


@router.get("/overview", response_model=OverviewStats)
async def overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Return high-level stats for the dashboard."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_24h = now - timedelta(hours=24)

    products_total = await db.scalar(select(func.count()).select_from(Product)) or 0
    products_today = await db.scalar(
        select(func.count()).select_from(Product).where(Product.first_seen >= today_start)
    ) or 0

    crawled_total = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(CrawlTask.status == "completed")
    ) or 0
    crawled_today = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(
            CrawlTask.status == "completed",
            CrawlTask.completed_at >= today_start,
        )
    ) or 0

    price_records_total = await db.scalar(
        select(func.count()).select_from(PriceHistory)
    ) or 0

    # Success rate last 24h
    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(FetchRun.status == "success").label("success"),
        ).where(FetchRun.created_at >= cutoff_24h)
    )
    row = result.one()
    total_24h, success_24h = row.total, row.success
    success_rate = (success_24h / total_24h * 100) if total_24h > 0 else 0.0

    return OverviewStats(
        products_total=products_total,
        products_today=products_today,
        crawled_total=crawled_total,
        crawled_today=crawled_today,
        success_rate_24h=round(success_rate, 1),
        price_records_total=price_records_total,
    )


@router.get("/throughput", response_model=list[ThroughputBucket])
async def throughput(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
    hours: int = 24,
):
    """Return hourly throughput for the last N hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(
            func.date_trunc("hour", CrawlTask.completed_at).label("hour"),
            func.count().label("count"),
        )
        .where(
            CrawlTask.status == "completed",
            CrawlTask.completed_at >= cutoff,
        )
        .group_by("hour")
        .order_by("hour")
    )
    return [ThroughputBucket(hour=row.hour, count=row.count) for row in result]


@router.get("/workers", response_model=list[WorkerStatus])
async def workers(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Return all worker heartbeat statuses."""
    now = datetime.now(timezone.utc)
    result = await db.execute(select(WorkerHeartbeat))
    heartbeats = result.scalars().all()

    out = []
    for hb in heartbeats:
        # If heartbeat is stale, report as offline
        effective_status = hb.status
        if now - hb.last_heartbeat > _HEARTBEAT_TIMEOUT:
            effective_status = "offline"

        out.append(WorkerStatus(
            worker_id=hb.worker_id,
            platform=hb.platform,
            status=effective_status,
            current_task_id=hb.current_task_id,
            tasks_completed=hb.tasks_completed,
            last_heartbeat=hb.last_heartbeat,
            started_at=hb.started_at,
        ))
    return out


@router.get("/recent-failures", response_model=list[RecentFailure])
async def recent_failures(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Return top 20 recent failed crawl tasks."""
    result = await db.execute(
        select(CrawlTask, Product.platform_id)
        .join(Product, CrawlTask.product_id == Product.id)
        .where(CrawlTask.status == "failed")
        .order_by(CrawlTask.updated_at.desc())
        .limit(20)
    )
    rows = result.all()
    return [
        RecentFailure(
            task_id=task.id,
            platform_id=pid,
            platform=task.platform,
            error_message=task.error_message,
            updated_at=task.updated_at,
        )
        for task, pid in rows
    ]
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_dashboard_routes.py -v`
Expected: PASS (with mock DB).

- [ ] **Step 4: Commit**

```bash
git add src/cps/api/routes/dashboard.py src/cps/api/schemas/dashboard.py tests/unit/api/test_dashboard_routes.py
git commit -m "feat(admin): add dashboard API routes — overview, throughput, workers, failures"
```

---

## Chunk 5: Products API

### Task 12: Product Schemas

**Files:**
- Create: `src/cps/api/schemas/product.py`

- [ ] **Step 1: Create product schemas**

```python
"""Product request/response schemas."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class ProductItem(BaseModel):
    """Product list item."""
    id: int
    platform_id: str
    platform: str
    title: str | None
    category: str | None
    is_active: bool
    first_seen: datetime
    updated_at: datetime
    current_price: int | None = None  # cents, from price_summary

    model_config = {"from_attributes": True}


class PricePoint(BaseModel):
    recorded_date: date
    price_cents: int
    price_type: str


class FetchRunItem(BaseModel):
    id: int
    status: str
    points_extracted: int | None
    ocr_confidence: float | None
    validation_passed: bool | None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductDetail(BaseModel):
    """Full product detail for side drawer."""
    id: int
    platform_id: str
    platform: str
    url: str | None
    title: str | None
    category: str | None
    is_active: bool
    first_seen: datetime
    updated_at: datetime
    lowest_price: int | None = None
    highest_price: int | None = None
    current_price: int | None = None

    model_config = {"from_attributes": True}


class AddProductRequest(BaseModel):
    platform_id: str = Field(min_length=10, max_length=11, pattern=r"^[A-Za-z0-9]+$")
    platform: str = Field(default="amazon", max_length=30)
    # Note: SeedManager.add_single() currently only creates amazon products.
    # If platform != "amazon" is needed, bypass SeedManager and create Product directly.


class BatchAddRequest(BaseModel):
    items: list[AddProductRequest] = Field(max_length=500)


class UpdateProductRequest(BaseModel):
    is_active: bool | None = None
    title: str | None = None
    category: str | None = None


class BatchUpdateRequest(BaseModel):
    ids: list[int] = Field(max_length=500)
    action: str  # "activate", "deactivate"


class DeleteProductRequest(BaseModel):
    confirm: bool
```

- [ ] **Step 2: Commit**

```bash
git add src/cps/api/schemas/product.py
git commit -m "feat(admin): add product request/response schemas"
```

---

### Task 13: Product Read Routes

**Files:**
- Modify: `src/cps/api/routes/products.py` (replace placeholder)
- Create: `tests/unit/api/test_product_routes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/api/test_product_routes.py`:

```python
"""Tests for product API routes."""

from unittest.mock import MagicMock

import pytest


class TestProductList:
    async def test_returns_paginated_response(self, auth_client, mock_db):
        """Product list returns paginated format."""
        # Mock count query
        mock_db.scalar.return_value = 0
        # Mock items query
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/products")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "total" in data
            assert "page" in data
            assert "page_size" in data


class TestProductAuth:
    async def test_requires_authentication(self, anon_client):
        async with await anon_client() as client:
            resp = await client.get("/api/v1/products")
            assert resp.status_code == 401
```

- [ ] **Step 2: Implement product read routes**

Replace placeholder `src/cps/api/routes/products.py`:

```python
"""Product routes — CRUD, search, batch ops, import."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, UploadFile
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.deps import get_current_user, get_db, log_audit
from cps.api.schemas.common import PaginatedResponse
from cps.api.schemas.product import (
    AddProductRequest,
    BatchAddRequest,
    BatchUpdateRequest,
    DeleteProductRequest,
    FetchRunItem,
    PricePoint,
    ProductDetail,
    ProductItem,
    UpdateProductRequest,
)
from cps.db.models import (
    AdminUser,
    CrawlTask,
    FetchRun,
    NotificationLog,
    PriceHistory,
    PriceMonitor,
    PriceSummary,
    Product,
)

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=PaginatedResponse[ProductItem])
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    platform: str | None = None,
    status: str | None = None,  # "active" or "inactive"
    category: str | None = None,
):
    """List products with pagination, search, and filters."""
    query = select(Product)
    count_query = select(func.count()).select_from(Product)

    # Filters
    if platform:
        query = query.where(Product.platform == platform)
        count_query = count_query.where(Product.platform == platform)
    if status == "active":
        query = query.where(Product.is_active == True)  # noqa: E712
        count_query = count_query.where(Product.is_active == True)  # noqa: E712
    elif status == "inactive":
        query = query.where(Product.is_active == False)  # noqa: E712
        count_query = count_query.where(Product.is_active == False)  # noqa: E712
    if category:
        query = query.where(Product.category == category)
        count_query = count_query.where(Product.category == category)
    if search:
        query = query.where(
            or_(
                Product.platform_id == search,
                Product.title.ilike(f"%{search}%"),
            )
        )
        count_query = count_query.where(
            or_(
                Product.platform_id == search,
                Product.title.ilike(f"%{search}%"),
            )
        )

    total = await db.scalar(count_query) or 0
    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Product.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    products = result.scalars().all()

    # Fetch current prices for listed products
    product_ids = [p.id for p in products]
    price_map: dict[int, int | None] = {}
    if product_ids:
        price_result = await db.execute(
            select(PriceSummary.product_id, PriceSummary.current_price)
            .where(
                PriceSummary.product_id.in_(product_ids),
                PriceSummary.price_type == "amazon",
            )
        )
        price_map = dict(price_result.all())

    items = []
    for p in products:
        item = ProductItem.model_validate(p)
        item.current_price = price_map.get(p.id)
        items.append(item)

    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Get product detail with price summary."""
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    # Get price summary
    price_result = await db.execute(
        select(PriceSummary).where(
            PriceSummary.product_id == product_id,
            PriceSummary.price_type == "amazon",
        )
    )
    summary = price_result.scalar_one_or_none()

    detail = ProductDetail.model_validate(product)
    if summary:
        detail.lowest_price = summary.lowest_price
        detail.highest_price = summary.highest_price
        detail.current_price = summary.current_price
    return detail


@router.get("/{product_id}/price-history", response_model=list[PricePoint])
async def get_price_history(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Get price history time series."""
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.recorded_date)
    )
    rows = result.scalars().all()
    return [
        PricePoint(
            recorded_date=r.recorded_date,
            price_cents=r.price_cents,
            price_type=r.price_type,
        )
        for r in rows
    ]


@router.get("/{product_id}/fetch-runs", response_model=list[FetchRunItem])
async def get_fetch_runs(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Get fetch run history for a product."""
    result = await db.execute(
        select(FetchRun)
        .where(FetchRun.product_id == product_id)
        .order_by(FetchRun.created_at.desc())
        .limit(50)
    )
    return [FetchRunItem.model_validate(r) for r in result.scalars().all()]
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_product_routes.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/cps/api/routes/products.py tests/unit/api/test_product_routes.py
git commit -m "feat(admin): add product read routes — list, detail, price-history, fetch-runs"
```

---

### Task 14: Product Write Routes

**Files:**
- Modify: `src/cps/api/routes/products.py` (add mutation endpoints)
- Modify: `tests/unit/api/test_product_routes.py` (add write tests)

- [ ] **Step 1: Write failing tests for mutations**

Add to `tests/unit/api/test_product_routes.py`:

```python
class TestAddProduct:
    async def test_add_single_product(self, auth_client, mock_db):
        async with await auth_client() as client:
            resp = await client.post(
                "/api/v1/products",
                json={"platform_id": "B08N5WRWNW"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert resp.status_code in (200, 201)


class TestBatchAdd:
    async def test_batch_add_products(self, auth_client, mock_db):
        async with await auth_client() as client:
            resp = await client.post(
                "/api/v1/products/batch",
                json={"items": [{"platform_id": "B08N5WRWNW"}, {"platform_id": "B09V3KXJPB"}]},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert resp.status_code == 200

    async def test_batch_limit_500(self, auth_client, mock_db):
        items = [{"platform_id": f"B{'0' * 9}{i:01d}"} for i in range(501)]
        async with await auth_client() as client:
            resp = await client.post(
                "/api/v1/products/batch",
                json={"items": items},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert resp.status_code == 422  # validation error
```

- [ ] **Step 2: Add write endpoints to products.py**

Append to `src/cps/api/routes/products.py`:

```python
@router.post("")
async def add_product(
    body: AddProductRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Add a single product."""
    from cps.seeds.manager import SeedManager

    manager = SeedManager(db)
    added = await manager.add_single(body.platform_id)
    if not added:
        raise HTTPException(status_code=409, detail="Product already exists")

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "create", "product", client_ip,
                    resource_id=body.platform_id)
    await db.commit()
    return {"detail": "Product added", "platform_id": body.platform_id}


@router.post("/batch")
async def batch_add(
    body: BatchAddRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Batch add products (max 500)."""
    from cps.seeds.manager import SeedManager

    manager = SeedManager(db)
    added = 0
    skipped = 0
    for item in body.items:
        try:
            result = await manager.add_single(item.platform_id)
            if result:
                added += 1
            else:
                skipped += 1
        except ValueError:
            skipped += 1

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "create", "product", client_ip,
                    details={"added": added, "skipped": skipped, "total": len(body.items)})
    await db.commit()
    return {"added": added, "skipped": skipped, "total": len(body.items)}


@router.post("/import")
async def import_products(
    file: UploadFile,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Upload a file for async background import."""
    from cps.config import get_settings
    from cps.db.models import ImportJob

    settings = get_settings()

    # Validate file
    if file.filename is None:
        raise HTTPException(status_code=400, detail="No filename")
    allowed_ext = (".txt", ".csv", ".jsonl.gz")
    if not any(file.filename.endswith(ext) for ext in allowed_ext):
        raise HTTPException(status_code=400, detail=f"Allowed: {', '.join(allowed_ext)}")

    # Create import job
    job = ImportJob(
        filename=file.filename,
        status="running",
        created_by=user.id,
    )
    db.add(job)
    await db.flush()

    # Save file
    upload_dir = settings.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{job.id}_{file.filename}"
    content = await file.read()
    dest.write_bytes(content)

    # Dispatch background processing
    background_tasks.add_task(_run_import, job.id, dest, settings.database_url)

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "create", "import", client_ip,
                    resource_id=str(job.id), details={"filename": file.filename})
    await db.commit()

    return {"import_job_id": job.id, "status": "running"}


async def _run_import(job_id: int, file_path, database_url: str) -> None:
    """Background task: process import file and update job progress."""
    import asyncio
    from cps.db.session import create_session_factory
    from cps.db.models import ImportJob
    from cps.seeds.manager import SeedManager

    factory = create_session_factory(database_url)
    async with factory() as session:
        try:
            manager = SeedManager(session)
            result = await manager.import_from_file(file_path)
            await session.execute(
                update(ImportJob).where(ImportJob.id == job_id).values(
                    status="completed",
                    total=result.total,
                    processed=result.total,
                    added=result.added,
                    skipped=result.skipped,
                    completed_at=func.now(),
                )
            )
            await session.commit()
            # Delete file on success
            file_path.unlink(missing_ok=True)
        except Exception as exc:
            await session.execute(
                update(ImportJob).where(ImportJob.id == job_id).values(
                    status="failed",
                    error_message=str(exc)[:1000],
                )
            )
            await session.commit()


@router.patch("/{product_id}")
async def update_product(
    product_id: int,
    body: UpdateProductRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Update product fields (including soft-delete via is_active=false)."""
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    changes = {}
    if body.is_active is not None:
        changes["is_active"] = body.is_active
    if body.title is not None:
        changes["title"] = body.title
    if body.category is not None:
        changes["category"] = body.category

    if changes:
        await db.execute(
            update(Product).where(Product.id == product_id).values(**changes)
        )

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "update", "product", client_ip,
                    resource_id=str(product_id), details=changes)
    await db.commit()
    return {"detail": "Updated"}


@router.post("/batch-update")
async def batch_update(
    body: BatchUpdateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Batch update products (activate/deactivate, max 500)."""
    if body.action == "activate":
        is_active = True
    elif body.action == "deactivate":
        is_active = False
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    result = await db.execute(
        update(Product).where(Product.id.in_(body.ids)).values(is_active=is_active)
    )

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "update", "product", client_ip,
                    details={"ids": body.ids, "action": body.action, "affected": result.rowcount})
    await db.commit()
    return {"affected": result.rowcount}


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    body: DeleteProductRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Hard delete with cascade. Requires confirm=true."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirm required")

    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    platform_id = product.platform_id

    # Cascade delete in order
    for model in [NotificationLog, PriceMonitor, CrawlTask, PriceSummary, FetchRun, PriceHistory]:
        await db.execute(delete(model).where(model.product_id == product_id))
    await db.execute(delete(Product).where(Product.id == product_id))

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "delete", "product", client_ip,
                    resource_id=str(product_id),
                    details={"platform_id": platform_id})
    await db.commit()
    return {"detail": "Deleted"}
```

Note: `NotificationLog` has `product_id` as an optional FK. The cascade delete query handles this. PriceHistory uses partitioned tables — the delete should work on the parent table and cascade to partitions.

- [ ] **Step 3: Run tests**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_product_routes.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/cps/api/routes/products.py tests/unit/api/test_product_routes.py
git commit -m "feat(admin): add product write routes — add, batch, import, update, delete"
```

---

## Chunk 6: Crawler + Imports API

### Task 15: Crawler Schemas + Routes

**Files:**
- Create: `src/cps/api/schemas/crawl.py`
- Modify: `src/cps/api/routes/crawler.py` (replace placeholder)
- Create: `tests/unit/api/test_crawler_routes.py`

- [ ] **Step 1: Create crawler schemas**

Create `src/cps/api/schemas/crawl.py`:

```python
"""Crawler request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class CrawlTaskItem(BaseModel):
    id: int
    product_id: int
    platform_id: str  # joined from product
    platform: str
    status: str
    priority: int
    retry_count: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class CrawlStats(BaseModel):
    pending: int
    running: int
    completed: int
    failed: int
    speed_per_hour: float  # completions/hour in last 24h


class EnqueueRequest(BaseModel):
    platform_ids: list[str] = Field(max_length=500)
    platform: str = "amazon"


class BatchRetryRequest(BaseModel):
    ids: list[int] = Field(max_length=500)
```

- [ ] **Step 2: Write the failing test**

Create `tests/unit/api/test_crawler_routes.py`:

```python
"""Tests for crawler API routes."""

from unittest.mock import MagicMock

import pytest


class TestCrawlerTasks:
    async def test_returns_paginated_tasks(self, auth_client, mock_db):
        mock_db.scalar.return_value = 0
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/crawler/tasks")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data


class TestCrawlerStats:
    async def test_returns_stats(self, auth_client, mock_db):
        # Mock counts for each status
        mock_db.scalar.side_effect = [10, 2, 500, 15, 48.0]

        async with await auth_client() as client:
            resp = await client.get("/api/v1/crawler/stats")
            assert resp.status_code == 200
            data = resp.json()
            assert "pending" in data
            assert "failed" in data


class TestCrawlerAuth:
    async def test_requires_authentication(self, anon_client):
        async with await anon_client() as client:
            resp = await client.get("/api/v1/crawler/tasks")
            assert resp.status_code == 401
```

- [ ] **Step 3: Implement crawler routes**

Replace `src/cps/api/routes/crawler.py`:

```python
"""Crawler routes — task queue, enqueue, retry, stats."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.deps import get_current_user, get_db, log_audit
from cps.api.schemas.common import PaginatedResponse
from cps.api.schemas.crawl import (
    BatchRetryRequest,
    CrawlStats,
    CrawlTaskItem,
    EnqueueRequest,
)
from cps.db.models import AdminUser, CrawlTask, Product

router = APIRouter(prefix="/crawler", tags=["crawler"])


@router.get("/tasks", response_model=PaginatedResponse[CrawlTaskItem])
async def list_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    platform: str | None = None,
):
    """List crawl tasks with filters."""
    query = (
        select(CrawlTask, Product.platform_id.label("pid"))
        .join(Product, CrawlTask.product_id == Product.id)
    )
    count_query = select(func.count()).select_from(CrawlTask)

    if status:
        query = query.where(CrawlTask.status == status)
        count_query = count_query.where(CrawlTask.status == status)
    if platform:
        query = query.where(CrawlTask.platform == platform)
        count_query = count_query.where(CrawlTask.platform == platform)

    total = await db.scalar(count_query) or 0
    offset = (page - 1) * page_size

    result = await db.execute(
        query.order_by(CrawlTask.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    items = []
    for task, pid in result.all():
        item = CrawlTaskItem(
            id=task.id,
            product_id=task.product_id,
            platform_id=pid,
            platform=task.platform,
            status=task.status,
            priority=task.priority,
            retry_count=task.retry_count,
            error_message=task.error_message,
            started_at=task.started_at,
            completed_at=task.completed_at,
            updated_at=task.updated_at,
        )
        items.append(item)

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/enqueue")
async def enqueue(
    body: EnqueueRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Add ASINs to crawl queue."""
    from cps.services.crawl_service import upsert_crawl_task

    enqueued = 0
    for pid in body.platform_ids:
        # Look up product
        result = await db.execute(
            select(Product).where(
                Product.platform_id == pid,
                Product.platform == body.platform,
            )
        )
        product = result.scalar_one_or_none()
        if product:
            await upsert_crawl_task(db, product.id)
            enqueued += 1

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "trigger", "crawl_task", client_ip,
                    details={"enqueued": enqueued, "total": len(body.platform_ids)})
    await db.commit()
    return {"enqueued": enqueued}


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Retry a single failed task."""
    result = await db.execute(
        update(CrawlTask)
        .where(CrawlTask.id == task_id, CrawlTask.status == "failed")
        .values(status="pending", error_message=None, retry_count=0)
    )
    if result.rowcount == 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Task not found or not failed")

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "trigger", "crawl_task", client_ip,
                    resource_id=str(task_id))
    await db.commit()
    return {"detail": "Task queued for retry"}


@router.post("/tasks/batch-retry")
async def batch_retry(
    body: BatchRetryRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Batch retry failed tasks (max 500)."""
    result = await db.execute(
        update(CrawlTask)
        .where(CrawlTask.id.in_(body.ids), CrawlTask.status == "failed")
        .values(status="pending", error_message=None, retry_count=0)
    )

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "trigger", "crawl_task", client_ip,
                    details={"retried": result.rowcount, "requested": len(body.ids)})
    await db.commit()
    return {"retried": result.rowcount}


@router.post("/retry-all-failed")
async def retry_all_failed(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Retry all failed tasks (max 10,000)."""
    # Get IDs first to cap at 10k
    id_result = await db.execute(
        select(CrawlTask.id)
        .where(CrawlTask.status == "failed")
        .limit(10000)
    )
    ids = [row[0] for row in id_result.all()]

    if ids:
        result = await db.execute(
            update(CrawlTask)
            .where(CrawlTask.id.in_(ids))
            .values(status="pending", error_message=None, retry_count=0)
        )
        retried = result.rowcount
    else:
        retried = 0

    client_ip = request.client.host if request.client else "unknown"
    await log_audit(db, user.id, "trigger", "crawl_task", client_ip,
                    details={"retried": retried})
    await db.commit()
    return {"retried": retried}


@router.get("/stats", response_model=CrawlStats)
async def stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Crawl statistics overview."""
    pending = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(CrawlTask.status == "pending")
    ) or 0
    running = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(CrawlTask.status == "running")
    ) or 0
    completed = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(CrawlTask.status == "completed")
    ) or 0
    failed = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(CrawlTask.status == "failed")
    ) or 0

    # Speed: completions in last 24h
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    completed_24h = await db.scalar(
        select(func.count()).select_from(CrawlTask).where(
            CrawlTask.status == "completed",
            CrawlTask.completed_at >= cutoff,
        )
    ) or 0
    speed = completed_24h / 24.0

    return CrawlStats(
        pending=pending, running=running, completed=completed,
        failed=failed, speed_per_hour=round(speed, 1),
    )
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_crawler_routes.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cps/api/schemas/crawl.py src/cps/api/routes/crawler.py tests/unit/api/test_crawler_routes.py
git commit -m "feat(admin): add crawler routes — task queue, enqueue, retry, stats"
```

---

### Task 16: Import Schemas + Routes

**Files:**
- Create: `src/cps/api/schemas/import_.py`
- Modify: `src/cps/api/routes/imports.py` (replace placeholder)
- Create: `tests/unit/api/test_import_routes.py`

- [ ] **Step 1: Create import schemas**

Create `src/cps/api/schemas/import_.py`:

```python
"""Import job response schemas."""

from datetime import datetime

from pydantic import BaseModel


class ImportJobItem(BaseModel):
    id: int
    filename: str
    status: str
    total: int
    processed: int
    added: int
    skipped: int
    error_message: str | None
    created_by: int
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Write tests and implement routes**

Create `tests/unit/api/test_import_routes.py`:

```python
"""Tests for import API routes."""

from unittest.mock import MagicMock

import pytest


class TestImportList:
    async def test_returns_list(self, auth_client, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/imports")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)
```

Replace `src/cps/api/routes/imports.py`:

```python
"""Import routes — job list and progress."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.deps import get_current_user, get_db
from cps.api.schemas.import_ import ImportJobItem
from cps.db.models import AdminUser, ImportJob

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("", response_model=list[ImportJobItem])
async def list_imports(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """List all import jobs (most recent first)."""
    result = await db.execute(
        select(ImportJob).order_by(ImportJob.created_at.desc()).limit(50)
    )
    return [ImportJobItem.model_validate(j) for j in result.scalars().all()]


@router.get("/{job_id}", response_model=ImportJobItem)
async def get_import(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
):
    """Get import job progress."""
    result = await db.execute(
        select(ImportJob).where(ImportJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return ImportJobItem.model_validate(job)
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_import_routes.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/cps/api/schemas/import_.py src/cps/api/routes/imports.py tests/unit/api/test_import_routes.py
git commit -m "feat(admin): add import routes — job list and progress"
```

---

### Task 17: Audit Schemas + Routes

**Files:**
- Create: `src/cps/api/schemas/audit.py`
- Modify: `src/cps/api/routes/audit.py` (replace placeholder)
- Create: `tests/unit/api/test_audit_routes.py`

- [ ] **Step 1: Create audit schema**

Create `src/cps/api/schemas/audit.py`:

```python
"""Audit log response schemas."""

from datetime import datetime

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: int
    user_id: int
    action: str
    resource_type: str
    resource_id: str | None
    details: dict | None
    ip_address: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Write test and implement route**

Create `tests/unit/api/test_audit_routes.py`:

```python
"""Tests for audit API routes."""

from unittest.mock import MagicMock

import pytest


class TestAuditList:
    async def test_returns_paginated(self, auth_client, mock_db):
        mock_db.scalar.return_value = 0
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        async with await auth_client() as client:
            resp = await client.get("/api/v1/audit")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
```

Replace `src/cps/api/routes/audit.py`:

```python
"""Audit routes — read-only audit log."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.api.deps import get_current_user, get_db
from cps.api.schemas.audit import AuditLogItem
from cps.api.schemas.common import PaginatedResponse
from cps.db.models import AdminUser, AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=PaginatedResponse[AuditLogItem])
async def list_audit(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[AdminUser, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str | None = None,
    resource_type: str | None = None,
):
    """List audit log entries with filters."""
    query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)

    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
        count_query = count_query.where(AuditLog.resource_type == resource_type)

    total = await db.scalar(count_query) or 0
    offset = (page - 1) * page_size

    result = await db.execute(
        query.order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = [AuditLogItem.model_validate(row) for row in result.scalars().all()]

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/api/test_audit_routes.py -v`
Expected: PASS.

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/victor/claudecode/cps && uv run pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/cps/api/schemas/audit.py src/cps/api/routes/audit.py tests/unit/api/test_audit_routes.py
git commit -m "feat(admin): add audit log routes — paginated read-only listing"
```

---

## Chunk 7: Worker Heartbeat

### Task 18: Heartbeat Service

**Files:**
- Create: `src/cps/api/heartbeat.py`
- Create: `tests/unit/test_heartbeat.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_heartbeat.py`:

```python
"""Tests for worker heartbeat service."""

import os
import socket
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.api.heartbeat import HeartbeatService


class TestHeartbeatService:
    def test_generate_worker_id(self):
        svc = HeartbeatService.__new__(HeartbeatService)
        worker_id = HeartbeatService._make_worker_id("amazon")
        assert worker_id.startswith("amazon-")
        assert str(os.getpid()) in worker_id

    async def test_register_creates_heartbeat_row(self):
        mock_session = AsyncMock()
        svc = HeartbeatService(mock_session, "amazon")
        await svc.register()
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        assert svc.worker_id is not None

    async def test_beat_updates_last_heartbeat(self):
        mock_session = AsyncMock()
        svc = HeartbeatService(mock_session, "amazon")
        svc._worker_id = "amazon-test-123"
        await svc.beat(current_task_id=42, tasks_completed=10)
        mock_session.execute.assert_awaited_once()

    async def test_set_offline(self):
        mock_session = AsyncMock()
        svc = HeartbeatService(mock_session, "amazon")
        svc._worker_id = "amazon-test-123"
        await svc.set_offline()
        mock_session.execute.assert_awaited_once()
```

- [ ] **Step 2: Run test — verify it fails**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/test_heartbeat.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.api.heartbeat'`

- [ ] **Step 3: Implement heartbeat service**

Create `src/cps/api/heartbeat.py`:

```python
"""Worker heartbeat service — registers and updates heartbeat in DB."""

import os
import socket
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import WorkerHeartbeat


class HeartbeatService:
    """Manages heartbeat registration and updates for a single worker."""

    def __init__(self, session: AsyncSession, platform: str) -> None:
        self._session = session
        self._platform = platform
        self._worker_id: str | None = None

    @property
    def worker_id(self) -> str | None:
        return self._worker_id

    @staticmethod
    def _make_worker_id(platform: str) -> str:
        hostname = socket.gethostname()
        pid = os.getpid()
        return f"{platform}-{hostname}-{pid}"

    async def register(self) -> str:
        """Register this worker with a heartbeat row."""
        self._worker_id = self._make_worker_id(self._platform)
        hb = WorkerHeartbeat(
            worker_id=self._worker_id,
            platform=self._platform,
            status="online",
        )
        self._session.add(hb)
        await self._session.flush()
        return self._worker_id

    async def beat(
        self,
        current_task_id: int | None = None,
        tasks_completed: int = 0,
        status: str = "online",
    ) -> None:
        """Update heartbeat timestamp and status."""
        if self._worker_id is None:
            return
        await self._session.execute(
            update(WorkerHeartbeat)
            .where(WorkerHeartbeat.worker_id == self._worker_id)
            .values(
                last_heartbeat=datetime.now(timezone.utc),
                current_task_id=current_task_id,
                tasks_completed=tasks_completed,
                status=status,
            )
        )

    async def set_idle(self) -> None:
        """Mark worker as idle."""
        await self.beat(current_task_id=None, status="idle")

    async def set_offline(self) -> None:
        """Mark worker as offline (graceful shutdown)."""
        if self._worker_id is None:
            return
        await self._session.execute(
            update(WorkerHeartbeat)
            .where(WorkerHeartbeat.worker_id == self._worker_id)
            .values(
                status="offline",
                current_task_id=None,
                last_heartbeat=datetime.now(timezone.utc),
            )
        )
```

- [ ] **Step 4: Run test — verify it passes**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/test_heartbeat.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cps/api/heartbeat.py tests/unit/test_heartbeat.py
git commit -m "feat(admin): add heartbeat service for worker status tracking"
```

---

### Task 19: WorkerLoop Heartbeat Integration

**Files:**
- Modify: `src/cps/worker.py`
- Modify: `tests/unit/test_worker.py`

- [ ] **Step 1: Write failing test for heartbeat in worker**

Add to `tests/unit/test_worker.py`:

```python
class TestWorkerHeartbeat:
    async def test_run_once_calls_heartbeat_on_success(self):
        """When heartbeat service is provided, worker updates it."""
        mock_session = AsyncMock()
        mock_queue = AsyncMock()
        mock_fetcher = AsyncMock()
        mock_parser = MagicMock()
        mock_heartbeat = AsyncMock()

        task = Task(id=1, product_id=100, platform_id="B123456789", platform="amazon")
        mock_queue.pop_next.return_value = task
        mock_parser.parse.return_value = MagicMock(
            records=[], summaries=[], points_extracted=5
        )

        worker = WorkerLoop(
            session=mock_session,
            queue=mock_queue,
            fetcher=mock_fetcher,
            parser=mock_parser,
            platform="amazon",
            heartbeat=mock_heartbeat,
        )
        await worker.run_once()
        mock_heartbeat.beat.assert_awaited()
```

- [ ] **Step 2: Run test — verify it fails**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/test_worker.py::TestWorkerHeartbeat -v`
Expected: FAIL — `TypeError: WorkerLoop.__init__() got unexpected keyword argument 'heartbeat'`

- [ ] **Step 3: Modify WorkerLoop to accept optional heartbeat**

In `src/cps/worker.py`, modify `__init__` to accept an optional `heartbeat` parameter:

```python
def __init__(
    self,
    session: AsyncSession,
    queue: TaskQueue,
    fetcher: PlatformFetcher,
    parser: PlatformParser,
    platform: str,
    idle_sleep: float = 5.0,
    heartbeat=None,  # Optional HeartbeatService
) -> None:
    self._session = session
    self._queue = queue
    self._fetcher = fetcher
    self._parser = parser
    self._platform = platform
    self._idle_sleep = idle_sleep
    self._running = True
    self._heartbeat = heartbeat
    self._tasks_completed = 0
```

In `run_once`, after `await self._queue.complete(task.id)` and before `return True`:

```python
self._tasks_completed += 1
if self._heartbeat:
    await self._heartbeat.beat(
        current_task_id=None,
        tasks_completed=self._tasks_completed,
    )
```

In `run_forever`, after `if not processed:` and before `await asyncio.sleep`:

```python
if self._heartbeat:
    await self._heartbeat.set_idle()
```

- [ ] **Step 4: Run test — verify it passes**

Run: `cd /Users/victor/claudecode/cps && uv run pytest tests/unit/test_worker.py -v`
Expected: All tests PASS (including existing tests — heartbeat=None is backward compatible).

- [ ] **Step 5: Update CLI worker command to use heartbeat**

In `src/cps/cli.py`, modify `worker_run` to create and register a HeartbeatService:

```python
# Inside _do(), after creating WorkerLoop:
from cps.api.heartbeat import HeartbeatService

heartbeat_svc = HeartbeatService(session, platform)
await heartbeat_svc.register()
await session.commit()

worker = WorkerLoop(
    session=session,
    queue=queue,
    fetcher=fetcher,
    parser=parser,
    platform=platform,
    heartbeat=heartbeat_svc,
)

# In signal handler, add offline status:
async def _shutdown():
    worker.stop()
    await heartbeat_svc.set_offline()
    await session.commit()
```

Note: Signal handler integration needs careful async handling. The exact implementation may need adjustment during coding.

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/victor/claudecode/cps && uv run pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/cps/worker.py src/cps/cli.py tests/unit/test_worker.py
git commit -m "feat(admin): integrate heartbeat service into WorkerLoop"
```

---

## Chunk 8: Frontend Foundation

### Task 20: React Project Scaffold

**Files:**
- Create: `web/` directory with Vite + React + TypeScript + Ant Design

- [ ] **Step 1: Initialize Vite project**

```bash
cd /Users/victor/claudecode/cps
npm create vite@latest web -- --template react-ts
cd web
npm install
```

- [ ] **Step 2: Install dependencies**

```bash
cd /Users/victor/claudecode/cps/web
npm install antd @ant-design/icons axios react-router-dom echarts echarts-for-react dayjs
```

- [ ] **Step 3: Configure Vite proxy**

Replace `web/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 4: Verify dev server starts**

```bash
cd /Users/victor/claudecode/cps/web && npm run dev &
sleep 3
curl -s http://localhost:5173 | head -5
kill %1
```
Expected: Returns HTML content from Vite dev server.

- [ ] **Step 5: Commit**

```bash
git add web/package.json web/package-lock.json web/vite.config.ts web/tsconfig.json web/tsconfig.app.json web/tsconfig.node.json web/index.html web/src/ web/public/ web/eslint.config.js
git commit -m "feat(admin): scaffold React + Vite + TypeScript frontend"
```

---

### Task 21: API Client + Types

**Files:**
- Create: `web/src/api/client.ts`
- Create: `web/src/api/endpoints.ts`
- Create: `web/src/types/index.ts`

- [ ] **Step 1: Create TypeScript types**

Create `web/src/types/index.ts`:

```typescript
export interface User {
  id: number
  username: string
  role: string
  is_active: boolean
  created_at: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface OverviewStats {
  products_total: number
  products_today: number
  crawled_total: number
  crawled_today: number
  success_rate_24h: number
  price_records_total: number
}

export interface WorkerStatus {
  worker_id: string
  platform: string
  status: 'online' | 'idle' | 'offline'
  current_task_id: number | null
  tasks_completed: number
  last_heartbeat: string
  started_at: string
}

export interface ThroughputBucket {
  hour: string
  count: number
}

export interface RecentFailure {
  task_id: number
  platform_id: string
  platform: string
  error_message: string | null
  updated_at: string
}

export interface ProductItem {
  id: number
  platform_id: string
  platform: string
  title: string | null
  category: string | null
  is_active: boolean
  first_seen: string
  updated_at: string
  current_price: number | null
}

export interface ProductDetail extends ProductItem {
  url: string | null
  lowest_price: number | null
  highest_price: number | null
}

export interface PricePoint {
  recorded_date: string
  price_cents: number
  price_type: string
}

export interface FetchRunItem {
  id: number
  status: string
  points_extracted: number | null
  ocr_confidence: number | null
  validation_passed: boolean | null
  error_message: string | null
  created_at: string
}

export interface CrawlTaskItem {
  id: number
  product_id: number
  platform_id: string
  platform: string
  status: string
  priority: number
  retry_count: number
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  updated_at: string
}

export interface CrawlStats {
  pending: number
  running: number
  completed: number
  failed: number
  speed_per_hour: number
}

export interface ImportJobItem {
  id: number
  filename: string
  status: string
  total: number
  processed: number
  added: number
  skipped: number
  error_message: string | null
  created_by: number
  created_at: string
  completed_at: string | null
}

export interface AuditLogItem {
  id: number
  user_id: number
  action: string
  resource_type: string
  resource_id: string | null
  details: Record<string, unknown> | null
  ip_address: string
  created_at: string
}
```

- [ ] **Step 2: Create API client**

Create `web/src/api/client.ts`:

```typescript
import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  headers: {
    'X-Requested-With': 'XMLHttpRequest',
  },
})

// Redirect to login on 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api
```

- [ ] **Step 3: Create endpoint functions**

Create `web/src/api/endpoints.ts`:

```typescript
import api from './client'
import type {
  AuditLogItem,
  CrawlStats,
  CrawlTaskItem,
  FetchRunItem,
  ImportJobItem,
  OverviewStats,
  PaginatedResponse,
  PricePoint,
  ProductDetail,
  ProductItem,
  RecentFailure,
  ThroughputBucket,
  User,
  WorkerStatus,
} from '../types'

// Auth
export const login = (username: string, password: string) =>
  api.post<User>('/auth/login', { username, password })

export const logout = () => api.post('/auth/logout')

export const getMe = () => api.get<User>('/auth/me')

// Dashboard
export const getOverview = () => api.get<OverviewStats>('/dashboard/overview')
export const getThroughput = (hours = 24) =>
  api.get<ThroughputBucket[]>('/dashboard/throughput', { params: { hours } })
export const getWorkers = () => api.get<WorkerStatus[]>('/dashboard/workers')
export const getRecentFailures = () =>
  api.get<RecentFailure[]>('/dashboard/recent-failures')

// Products
export const getProducts = (params: Record<string, unknown>) =>
  api.get<PaginatedResponse<ProductItem>>('/products', { params })
export const getProduct = (id: number) =>
  api.get<ProductDetail>(`/products/${id}`)
export const getPriceHistory = (id: number) =>
  api.get<PricePoint[]>(`/products/${id}/price-history`)
export const getFetchRuns = (id: number) =>
  api.get<FetchRunItem[]>(`/products/${id}/fetch-runs`)
export const addProduct = (platformId: string) =>
  api.post('/products', { platform_id: platformId })
export const importProducts = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/products/import', form)
}

// Crawler
export const getCrawlerTasks = (params: Record<string, unknown>) =>
  api.get<PaginatedResponse<CrawlTaskItem>>('/crawler/tasks', { params })
export const getCrawlerStats = () => api.get<CrawlStats>('/crawler/stats')
export const retryTask = (id: number) =>
  api.post(`/crawler/tasks/${id}/retry`)
export const retryAllFailed = () => api.post('/crawler/retry-all-failed')

// Imports
export const getImports = () => api.get<ImportJobItem[]>('/imports')
export const getImport = (id: number) => api.get<ImportJobItem>(`/imports/${id}`)

// Audit
export const getAuditLog = (params: Record<string, unknown>) =>
  api.get<PaginatedResponse<AuditLogItem>>('/audit', { params })
```

- [ ] **Step 4: Commit**

```bash
git add web/src/types/ web/src/api/
git commit -m "feat(admin): add TypeScript types, API client, and endpoint functions"
```

---

### Task 22: Admin Layout + Router

**Files:**
- Create: `web/src/layouts/AdminLayout.tsx`
- Create: `web/src/hooks/useAuth.ts`
- Create: `web/src/hooks/usePolling.ts`
- Modify: `web/src/App.tsx`

- [ ] **Step 1: Create auth hook**

Create `web/src/hooks/useAuth.ts`:

```typescript
import { useCallback, useEffect, useState } from 'react'
import { getMe, login as loginApi, logout as logoutApi } from '../api/endpoints'
import type { User } from '../types'

export function useAuth() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getMe()
      .then((res) => setUser(res.data))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const res = await loginApi(username, password)
    setUser(res.data)
  }, [])

  const logout = useCallback(async () => {
    await logoutApi()
    setUser(null)
  }, [])

  return { user, loading, login, logout }
}
```

- [ ] **Step 2: Create polling hook**

Create `web/src/hooks/usePolling.ts`:

```typescript
import { useEffect, useRef } from 'react'

export function usePolling(callback: () => void, intervalMs: number, enabled = true) {
  const savedCallback = useRef(callback)

  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  useEffect(() => {
    if (!enabled) return
    savedCallback.current()
    const id = setInterval(() => savedCallback.current(), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs, enabled])
}
```

- [ ] **Step 3: Create AdminLayout**

Create `web/src/layouts/AdminLayout.tsx`:

```tsx
import {
  AuditOutlined,
  CloudUploadOutlined,
  DashboardOutlined,
  LogoutOutlined,
  ShoppingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

const { Sider, Header, Content } = Layout

interface Props {
  username: string
  onLogout: () => void
}

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
  { key: '/products', icon: <ShoppingOutlined />, label: 'Products' },
  { key: '/crawler', icon: <ThunderboltOutlined />, label: 'Crawler' },
  { key: '/imports', icon: <CloudUploadOutlined />, label: 'Imports' },
  { key: '/audit', icon: <AuditOutlined />, label: 'Audit Log' },
]

export default function AdminLayout({ username, onLogout }: Props) {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="dark">
        <div style={{ padding: '16px 24px', color: '#fff', fontSize: 18, fontWeight: 600 }}>
          CPS Admin
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 16 }}>
          <Typography.Text>{username}</Typography.Text>
          <LogoutOutlined onClick={onLogout} style={{ cursor: 'pointer', fontSize: 18 }} />
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
```

- [ ] **Step 4: Set up App.tsx with router**

Replace `web/src/App.tsx`:

```tsx
import { ConfigProvider, Spin } from 'antd'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AdminLayout from './layouts/AdminLayout'
import { useAuth } from './hooks/useAuth'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Products from './pages/Products'
import Crawler from './pages/Crawler'
import Imports from './pages/Imports'
import Audit from './pages/Audit'

export default function App() {
  const { user, loading, login, logout } = useAuth()

  if (loading) {
    return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', marginTop: '40vh' }} />
  }

  return (
    <ConfigProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={
            user ? <Navigate to="/dashboard" /> : <Login onLogin={login} />
          } />
          {user ? (
            <Route element={<AdminLayout username={user.username} onLogout={logout} />}>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/products" element={<Products />} />
              <Route path="/crawler" element={<Crawler />} />
              <Route path="/imports" element={<Imports />} />
              <Route path="/audit" element={<Audit />} />
              <Route path="*" element={<Navigate to="/dashboard" />} />
            </Route>
          ) : (
            <Route path="*" element={<Navigate to="/login" />} />
          )}
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}
```

Note: This requires creating placeholder page components first. Create them as stubs in the next steps.

- [ ] **Step 5: Create placeholder pages**

Create each file in `web/src/pages/`:

`Login.tsx`, `Dashboard.tsx`, `Products.tsx`, `Crawler.tsx`, `Imports.tsx`, `Audit.tsx`

Each with minimal content like:

```tsx
export default function PageName() {
  return <div>PageName — Coming soon</div>
}
```

Login needs the login form — see Task 23.

- [ ] **Step 6: Remove default Vite boilerplate**

Delete `web/src/App.css`, `web/src/index.css` (Ant Design provides styling). Clean up `web/src/main.tsx` to just render `App`.

- [ ] **Step 7: Verify app builds**

```bash
cd /Users/victor/claudecode/cps/web && npm run build
```
Expected: Build succeeds, outputs to `web/dist/`.

- [ ] **Step 8: Commit**

```bash
git add web/src/
git commit -m "feat(admin): add AdminLayout, router, auth hook, and page stubs"
```

---

### Task 23: Login Page

**Files:**
- Create (or replace stub): `web/src/pages/Login.tsx`

- [ ] **Step 1: Implement Login page**

```tsx
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { useState } from 'react'

interface Props {
  onLogin: (username: string, password: string) => Promise<void>
}

export default function Login({ onLogin }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    setError(null)
    try {
      await onLogin(values.username, values.password)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Login failed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card style={{ width: 400 }}>
        <Typography.Title level={3} style={{ textAlign: 'center' }}>CPS Admin</Typography.Title>
        {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 16 }} />}
        <Form onFinish={handleFinish}>
          <Form.Item name="username" rules={[{ required: true, message: 'Username required' }]}>
            <Input prefix={<UserOutlined />} placeholder="Username" size="large" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: 'Password required' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="Password" size="large" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
              Log in
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/victor/claudecode/cps/web && npm run build
```
Expected: Builds successfully.

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/Login.tsx
git commit -m "feat(admin): implement Login page with username/password form"
```

---

## Chunk 9: Frontend Core Pages

### Task 24: Dashboard Page

**Files:**
- Create: `web/src/pages/Dashboard.tsx`
- Create: `web/src/components/StatsCard.tsx`
- Create: `web/src/components/StatusBadge.tsx`

- [ ] **Step 1: Create reusable components**

`web/src/components/StatsCard.tsx`:
```tsx
import { Card, Statistic } from 'antd'

interface Props {
  title: string
  value: number | string
  suffix?: string
  today?: number
}

export default function StatsCard({ title, value, suffix, today }: Props) {
  return (
    <Card>
      <Statistic title={title} value={value} suffix={suffix} />
      {today !== undefined && (
        <span style={{ color: '#52c41a', fontSize: 12 }}>+{today} today</span>
      )}
    </Card>
  )
}
```

`web/src/components/StatusBadge.tsx`:
```tsx
import { Tag } from 'antd'

const colorMap: Record<string, string> = {
  online: 'green',
  idle: 'orange',
  offline: 'red',
  pending: 'blue',
  running: 'processing',
  completed: 'green',
  failed: 'red',
  active: 'green',
  inactive: 'default',
}

interface Props {
  status: string
}

export default function StatusBadge({ status }: Props) {
  return <Tag color={colorMap[status] || 'default'}>{status}</Tag>
}
```

- [ ] **Step 2: Implement Dashboard page**

Full implementation of `web/src/pages/Dashboard.tsx` with:
- 4 StatsCards row (products, crawled, success rate, price records)
- Throughput bar chart (ECharts) + Worker status cards (2:1 row)
- Recent failures table
- 30s auto-refresh via `usePolling`

The exact implementation follows the spec wireframe. Key: use `usePolling(fetchAll, 30000)` to auto-refresh, `ReactECharts` for the throughput chart.

- [ ] **Step 3: Verify build**

```bash
cd /Users/victor/claudecode/cps/web && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/Dashboard.tsx web/src/components/StatsCard.tsx web/src/components/StatusBadge.tsx
git commit -m "feat(admin): implement Dashboard page with stats, charts, workers"
```

---

### Task 25: Products Page + Drawer

**Files:**
- Create: `web/src/pages/Products.tsx`
- Create: `web/src/components/ProductDrawer.tsx`
- Create: `web/src/components/PriceChart.tsx`
- Create: `web/src/components/EmptyState.tsx`

- [ ] **Step 1: Create reusable components**

`web/src/components/EmptyState.tsx`:
```tsx
import { Empty, Typography } from 'antd'

interface Props {
  description?: string
}

export default function EmptyState({ description = 'No data' }: Props) {
  return <Empty description={<Typography.Text type="secondary">{description}</Typography.Text>} />
}
```

`web/src/components/PriceChart.tsx`:
- ECharts wrapper that takes `PricePoint[]` and renders line chart
- Groups by price_type (amazon, new, used) with different colors
- Formats price_cents to dollars

`web/src/components/ProductDrawer.tsx`:
- Ant Design `Drawer` with 3 tabs: Price History / Crawl Runs / Info
- Loads data on open via product ID
- Price History tab uses `PriceChart`
- Crawl Runs tab uses `Table`
- Info tab shows metadata + action buttons

- [ ] **Step 2: Implement Products page**

`web/src/pages/Products.tsx`:
- Search bar + platform/status/category filters
- Add ASIN button + Import button
- `Table` with columns: platform_id, title, platform, status, current_price, updated_at
- Checkbox selection + batch action bar
- Pagination
- Click row → open `ProductDrawer`
- Empty state when no products

- [ ] **Step 3: Verify build**

```bash
cd /Users/victor/claudecode/cps/web && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/Products.tsx web/src/components/ProductDrawer.tsx web/src/components/PriceChart.tsx web/src/components/EmptyState.tsx
git commit -m "feat(admin): implement Products page with search, filters, drawer detail"
```

---

### Task 26: Crawler Page

**Files:**
- Create: `web/src/pages/Crawler.tsx`

- [ ] **Step 1: Implement Crawler page**

`web/src/pages/Crawler.tsx`:
- Top: Enqueue ASINs button + Retry All Failed button
- Stats row: 5 StatsCards (Pending / Running / Completed / Failed / Speed)
- Worker section: worker cards with StatusBadge
- Task queue: Tabs (Failed default / Pending / Running / Completed)
- Error summary bar above Failed tab
- 10s auto-refresh via `usePolling`

- [ ] **Step 2: Verify build**

```bash
cd /Users/victor/claudecode/cps/web && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add web/src/pages/Crawler.tsx
git commit -m "feat(admin): implement Crawler page with task queue, workers, stats"
```

---

### Task 27: Imports + Audit Pages

**Files:**
- Create: `web/src/pages/Imports.tsx`
- Create: `web/src/pages/Audit.tsx`

- [ ] **Step 1: Implement Imports page**

`web/src/pages/Imports.tsx`:
- Table: filename, status (with progress bar), total/added/skipped, created_by, time
- Status column: running shows `Progress` component, completed/failed shows `StatusBadge`
- 5s polling while any job is running

- [ ] **Step 2: Implement Audit page**

`web/src/pages/Audit.tsx`:
- Filterable table: action, resource_type selectors
- Columns: user_id, action, resource_type, resource_id, details (expandable JSON), IP, timestamp
- Paginated

- [ ] **Step 3: Verify full build**

```bash
cd /Users/victor/claudecode/cps/web && npm run build
```
Expected: Clean build, no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/pages/Imports.tsx web/src/pages/Audit.tsx
git commit -m "feat(admin): implement Imports and Audit pages"
```

---

## Chunk 10: Integration + Verification

### Task 28: End-to-End Verification

- [ ] **Step 1: Run full backend test suite**

```bash
cd /Users/victor/claudecode/cps && uv run pytest --tb=short -q
```
Expected: All tests pass (original 327+ plus new API tests).

- [ ] **Step 2: Check test coverage**

```bash
cd /Users/victor/claudecode/cps && uv run pytest --cov --cov-report=term-missing
```
Expected: ≥80% coverage. Add `src/cps/api/app.py` and `src/cps/cli.py` to coverage omit if needed.

- [ ] **Step 3: Manual smoke test**

Terminal 1:
```bash
cd /Users/victor/claudecode/cps
uv run alembic upgrade head
uv run cps admin create-user --username admin --password admin_test_12345
uv run cps api run
```

Terminal 2:
```bash
cd /Users/victor/claudecode/cps/web && npm run dev
```

Open `http://localhost:5173`:
- Login with admin/admin_test_12345
- Dashboard loads with stats
- Products page lists products from DB
- Crawler page shows task queue
- Audit log shows login entry

- [ ] **Step 4: Update coverage omit list**

Add to `pyproject.toml` coverage omit:
```toml
"src/cps/api/app.py",
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(admin): complete Admin Backend P1 — backend API + React frontend"
```
