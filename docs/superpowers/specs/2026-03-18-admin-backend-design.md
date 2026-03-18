# CPS Admin Backend — Design Spec

> Date: 2026-03-18
> Status: Draft
> Scope: Operations admin panel for CPS crawling system

## 1. Overview

Build an operations admin backend for the CPS price monitoring system. Primary user: project owner (PM). Purpose: monitor crawling health, manage ASIN inventory, control crawler tasks, and review data — replacing CLI as the main interface.

**Tech Stack:** FastAPI (backend API) + React + Vite + Ant Design (frontend), same as dalaowang project for consistency.

**Guiding Principle:** Design for long-term operations — proper auth, audit logging, runtime config, extensible architecture. Implement in three phases.

## 2. Architecture

### 2.1 Project Structure

```
cps/
├── src/cps/              # Existing code (crawler, data layer, CLI)
│   ├── api/              # [NEW] FastAPI API layer
│   │   ├── app.py        # FastAPI instance + middleware + conditional static file serving
│   │   ├── auth.py       # Password auth + cookie session management
│   │   ├── deps.py       # Dependency injection (DB session, current user)
│   │   ├── schemas/      # Pydantic response/request models
│   │   │   ├── auth.py
│   │   │   ├── product.py
│   │   │   ├── crawl.py
│   │   │   ├── stats.py
│   │   │   ├── config.py     # P2
│   │   │   └── scheduler.py  # P2
│   │   └── routes/       # API route handlers
│   │       ├── auth.py
│   │       ├── dashboard.py
│   │       ├── products.py
│   │       ├── crawler.py
│   │       ├── imports.py
│   │       ├── audit.py
│   │       ├── config.py     # P2
│   │       ├── scheduler.py  # P2
│   │       ├── logs.py       # P2
│   │       └── analytics.py  # P3
│   └── ...               # Existing modules untouched
├── web/                  # [NEW] React frontend
│   ├── src/
│   │   ├── layouts/      # AdminLayout (sidebar + header + content)
│   │   ├── pages/        # Page components
│   │   ├── components/   # Reusable components (PriceChart, StatusBadge, StatsCard)
│   │   ├── api/          # Axios client + endpoint functions
│   │   ├── hooks/        # Custom React hooks
│   │   ├── types/        # TypeScript type definitions
│   │   └── App.tsx       # React Router setup
│   ├── package.json
│   └── vite.config.ts    # Dev proxy to FastAPI
└── pyproject.toml        # Add fastapi, uvicorn, bcrypt dependencies
```

### 2.2 Key Architecture Decisions

1. **API layer reuses existing services** — `SeedManager`, `PipelineOrchestrator`, `DbTaskQueue`, `WorkerLoop` already encapsulate business logic. API routes are thin wrappers.
2. **Schemas separate from ORM models** — `api/schemas/` contains Pydantic response models, decoupled from SQLAlchemy models in `db/models.py`.
3. **Worker and API are independent processes** — `cps api run` (FastAPI/uvicorn) and `cps worker run` (crawler) run separately. Communication via database (heartbeat table, task queue).
4. **Static file serving is conditional** — `app.py` mounts `web/dist/` if it exists (production). In development, Vite dev server proxies to FastAPI.
5. **CLI and API coexist** — Both call the same service layer. CLI remains available for scripting and automation.

### 2.3 New CLI Command

```
cps api run        # Start FastAPI server (uvicorn)
cps admin create-user --username admin --password <pw>   # Create first admin user
```

### 2.4 Development Setup

Two terminals:
- Terminal 1: `uv run cps api run` (FastAPI on port 8000)
- Terminal 2: `cd web && npm run dev` (Vite on port 5173, proxies API to 8000)

## 3. Authentication & Security

### 3.1 Auth Flow

- Login: `POST /api/v1/auth/login` with username + password → sets HTTP-only cookie
- Session: `admin_sessions` table with `expires_at` (7-day TTL)
- Logout: `POST /api/v1/auth/logout` → clears cookie + deletes session row
- First user created via CLI: `cps admin create-user`

### 3.2 Password Storage

- bcrypt hash stored in `admin_users.password_hash`
- Never store plaintext passwords

### 3.3 Brute Force Protection

- Same IP: max 10 login attempts per 5 minutes
- Exceeded → 15-minute lockout
- Tracked in-memory (dict with TTL), not DB

### 3.4 CORS

- Development only (`DEBUG=true`): allow `http://localhost:5173`
- Production: same-origin (FastAPI serves static files), CORS disabled

### 3.5 CSRF Protection

Since auth uses cookies, CSRF protection is required:
- All mutating API requests must include `X-Requested-With: XMLHttpRequest` header
- FastAPI middleware rejects POST/PATCH/DELETE without this header (returns 403)
- Axios client sets this header globally in its default config
- This is sufficient because browsers block custom headers on cross-origin requests (CORS pre-flight), making cookie-based CSRF impossible

### 3.6 Session Token Details

- Generated via `secrets.token_urlsafe(32)` (43 URL-safe characters)
- Cookie name: `cps_session`
- Cookie attributes: `HttpOnly=true`, `SameSite=Lax`, `Path=/api`, `Secure=true` in production

### 3.7 OpenAPI Docs

- `/docs` and `/redoc` disabled when `DEBUG=false`

## 4. Database Changes

### 4.1 New Tables

#### P1 Tables

**admin_users**
| Column | Type | Notes |
|--------|------|-------|
| id | BigInteger PK | |
| username | String(50) UNIQUE | |
| password_hash | String(255) | bcrypt |
| role | String(20) | 'admin' / 'operator' / 'viewer' (P1: all are admin) |
| is_active | Boolean | default true |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

**admin_sessions**
| Column | Type | Notes |
|--------|------|-------|
| id | BigInteger PK | |
| user_id | FK → admin_users | |
| session_token | String(64) UNIQUE | `secrets.token_urlsafe(32)` |
| expires_at | DateTime(tz) | login_time + 7 days |
| created_at | DateTime(tz) | |

**worker_heartbeats**
| Column | Type | Notes |
|--------|------|-------|
| id | BigInteger PK | |
| worker_id | String(50) UNIQUE | `{platform}-{hostname}-{pid}`, e.g. "amazon-macbook-12345" |
| platform | String(30) | |
| status | String(20) | 'online' / 'idle' / 'offline' |
| current_task_id | BigInteger nullable | FK → crawl_tasks |
| tasks_completed | Integer | total since start |
| last_heartbeat | DateTime(tz) | updated every 10 seconds |
| started_at | DateTime(tz) | |

**Worker Heartbeat Integration (C-1 fix):**
- `worker_id` generation: `f"{platform}-{socket.gethostname()}-{os.getpid()}"` — unique per process
- `WorkerLoop` modification: add `_update_heartbeat()` method, called every 10 seconds (or after each task completion, whichever comes first)
- On startup: INSERT row with status='online'
- During processing: UPDATE last_heartbeat + current_task_id
- On idle (no pending tasks): UPDATE status='idle', current_task_id=NULL
- On graceful shutdown (SIGINT/SIGTERM): UPDATE status='offline'
- API staleness rule: if `now - last_heartbeat > 60s`, API reports worker as 'offline' regardless of DB status
- Heartbeat uses the existing DB session in WorkerLoop, no additional connections needed

**import_jobs**
| Column | Type | Notes |
|--------|------|-------|
| id | BigInteger PK | |
| filename | String(500) | original filename |
| status | String(20) | 'running' / 'completed' / 'failed' |
| total | Integer | total ASINs in file |
| processed | Integer | processed so far |
| added | Integer | newly added |
| skipped | Integer | duplicates |
| error_message | Text nullable | |
| created_by | FK → admin_users | |
| created_at | DateTime(tz) | |
| completed_at | DateTime(tz) nullable | |

**audit_log**
| Column | Type | Notes |
|--------|------|-------|
| id | BigInteger PK | |
| user_id | FK → admin_users | |
| action | String(50) | 'create' / 'update' / 'delete' / 'trigger' |
| resource_type | String(50) | 'product' / 'crawl_task' / 'import' / ... |
| resource_id | String(50) nullable | |
| details | JSONB nullable | what changed (PostgreSQL JSONB for queryability) |
| ip_address | String(45) | |
| created_at | DateTime(tz) | |

#### P2 Tables

**system_config**
| Column | Type | Notes |
|--------|------|-------|
| key | String(100) PK | e.g. 'ccc_rate_limit' |
| value | Text | JSON-encoded value |
| description | Text | human-readable description |
| updated_by | FK → admin_users | |
| updated_at | DateTime(tz) | |

**error_events** (replaces app_logs — only stores ERROR-level aggregates)
| Column | Type | Notes |
|--------|------|-------|
| id | BigInteger PK | |
| error_type | String(100) | e.g. 'HTTP_429', 'OCR_FAILED' |
| count | Integer | occurrences |
| last_message | Text | most recent error message sample |
| first_seen | DateTime(tz) | |
| last_seen | DateTime(tz) | |
| platform | String(30) nullable | |

UniqueConstraint on `(error_type, platform)`. Upsert strategy: `INSERT ON CONFLICT (error_type, platform) DO UPDATE SET count = count + 1, last_message = EXCLUDED.last_message, last_seen = EXCLUDED.last_seen`.

#### P3 Tables

**alert_rules** — alert condition definitions
**alert_events** — triggered alert instances

### 4.1.1 Existing Table Notes

**CrawlTask.requested_by_user_id** — existing FK to `telegram_users`. Admin-triggered crawl tasks (via `/crawler/enqueue`) leave this as NULL. Admin attribution is tracked separately in `audit_log`, which records who triggered what and when. No schema change needed.

**New ORM models** go into `src/cps/db/models.py` extending the existing `Base`. Alembic auto-generates migrations from the same `Base.metadata`.

### 4.2 Migration Strategy

- One Alembic migration per phase: `004_admin_backend_p1.py`, `005_admin_backend_p2.py`, `006_admin_backend_p3.py`
- P1 migration creates: admin_users, admin_sessions, worker_heartbeats, import_jobs, audit_log

### 4.3 Configuration Layers (P2)

- **Layer 1 (immutable):** `.env` via Pydantic Settings — database URL, API keys, secrets
- **Layer 2 (mutable):** `system_config` DB table — rate limits, retry counts, cooldown time
- Worker reads DB config at the start of each processing loop (already has DB session, minimal overhead)
- New `ConfigService` merges both layers, DB overrides env defaults for mutable keys

## 5. API Design

All endpoints prefixed with `/api/v1/`. All except `/auth/login` require authentication.

### 5.1 Common Conventions

**Pagination:**
```json
GET /products?page=1&page_size=20

Response:
{
  "items": [...],
  "total": 1234,
  "page": 1,
  "page_size": 20
}
```

**Error format:**
```json
{
  "detail": "Product not found",
  "code": "NOT_FOUND"
}
```

**Audit:** All POST/PATCH/DELETE requests automatically logged to `audit_log` via middleware. Captures: user_id, action, resource_type, resource_id, change details, IP, timestamp.

**Batch limits:** All batch operations capped at 500 items per request.

### 5.2 Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Login (rate-limited: 10/5min per IP) |
| POST | `/auth/logout` | Logout, clear session |
| GET | `/auth/me` | Current user info |

### 5.3 Dashboard

| Method | Path | Description |
|--------|------|-------------|
| GET | `/dashboard/overview` | Stats cards (totals + today's increments) |
| GET | `/dashboard/throughput` | Throughput time series (?hours=24, buckets of 60min) |
| GET | `/dashboard/recent-failures` | Top 20 recent failures |
| GET | `/dashboard/workers` | Worker heartbeat status list |

Overview response includes:
```json
{
  "products_total": 50000,
  "products_today": 120,
  "crawled_total": 32000,
  "crawled_today": 850,
  "success_rate_24h": 94.5,
  "price_records_total": 2100000
}
```

### 5.4 Products

| Method | Path | Description |
|--------|------|-------------|
| GET | `/products` | List (paginated, search, filter by platform/status/category) |
| GET | `/products/{id}` | Detail + price summary |
| GET | `/products/{id}/price-history` | Price time series (?start=&end=) |
| GET | `/products/{id}/fetch-runs` | Fetch run history list |
| POST | `/products` | Add single ASIN |
| POST | `/products/batch` | Batch add (JSON array, ≤500) |
| POST | `/products/import` | File upload → async background job (see 5.6.1) |
| PATCH | `/products/{id}` | Update (including soft-delete via is_active=false) |
| POST | `/products/batch-update` | Batch update (≤500 ids + action) |
| DELETE | `/products/{id}` | Hard delete with cascade (body: `{"confirm": true}` required) |

Search: `?search=` matches `platform_id` (exact, prioritized) and `title` (fuzzy).

Request schema for `POST /products`: `{"platform_id": "B0...", "platform": "amazon"}` — `platform` defaults to `"amazon"`.

Hard delete cascade order: notification_log → price_monitors → crawl_tasks → price_summary → fetch_runs → price_history → product. Note: price_history uses partitioned tables — cascade delete tested during implementation. Hard delete is a P1 feature but expected to be rarely used; soft-delete (PATCH is_active=false) is the default.

### 5.5 Crawler

| Method | Path | Description |
|--------|------|-------------|
| GET | `/crawler/tasks` | Task queue (paginated, filter by status/platform) |
| POST | `/crawler/enqueue` | Add ASINs to crawl queue (not direct execution) |
| POST | `/crawler/tasks/{id}/retry` | Retry single failed task |
| POST | `/crawler/tasks/batch-retry` | Batch retry (≤500 ids) |
| POST | `/crawler/retry-all-failed` | Retry all failed tasks (max 10,000 per call) |
| GET | `/crawler/stats` | Crawl statistics by platform/status |

### 5.6 Imports

| Method | Path | Description |
|--------|------|-------------|
| GET | `/imports` | Import job list |
| GET | `/imports/{id}` | Import progress (total/processed/added/skipped) |

#### 5.6.1 Import Execution Strategy (C-2 fix)

1. `POST /products/import` accepts file upload (≤100MB, .txt/.csv/.jsonl.gz only)
2. File saved to `{data_dir}/uploads/{import_job_id}_{filename}`
3. Creates `import_jobs` row with status='running', returns `import_job_id` immediately
4. Dispatches processing to `FastAPI BackgroundTasks` — calls `SeedManager.import_from_file()` (for .txt/.csv) or `dataset_importer.extract_asins_from_metadata()` + `submit_asins_in_batches()` (for .jsonl.gz)
5. Background task updates `import_jobs` row every 1000 ASINs: processed, added, skipped
6. On completion: sets status='completed' + completed_at. On error: status='failed' + error_message
7. Frontend polls `GET /imports/{id}` every 5 seconds while status='running'
8. Uploaded file deleted after successful completion, retained on failure for debugging

### 5.7 Audit

| Method | Path | Description |
|--------|------|-------------|
| GET | `/audit` | Audit log list (paginated, filter by action/resource_type) |

### 5.8 P2 Endpoints (reserved paths)

| Method | Path | Description |
|--------|------|-------------|
| GET/PUT | `/config` | Runtime config read/write |
| GET | `/scheduler/jobs` | Scheduled job list (APScheduler) |
| POST | `/scheduler/jobs/{id}/trigger` | Manual trigger |
| GET | `/logs` | Error event log (aggregated) |
| POST | `/crawler/workers/{id}/pause` | Pause worker (via DB control signal) |
| POST | `/crawler/workers/{id}/resume` | Resume worker |

## 6. Frontend Design

### 6.1 Layout

**Sidebar navigation (confirmed)** — left sidebar with grouped menu items, top header bar with user info/logout.

Sidebar menu groups:
- **Operations:** Dashboard, Products, Crawler, Imports
- **System:** Audit Log
- **P2 (grayed out):** Config, Scheduler, Logs
- **P3 (hidden until implemented):** Analytics

### 6.2 Pages

#### Login
- Username + password form, error message display
- Redirects to Dashboard on success

#### Dashboard
- **Row 1:** 4 stat cards (Products / Crawled / Success Rate / Price Records) with today's increment
- **Row 2:** 24h throughput bar chart (ECharts) + Worker status cards (side by side, 2:1 ratio)
- **Row 3:** Recent failures table (top 20)
- **Auto-refresh:** 30-second polling interval

#### Products
- **List view:** Search bar + platform/status/category filters + Add/Import buttons + data table with checkbox selection + pagination + batch action bar (appears when items selected)
- **Detail view (Side Drawer):** Right panel slides out on row click. Tabs: Price History (ECharts chart) / Crawl Runs (table) / Info (metadata + actions). Close button returns to list.
- **Empty state:** "No products yet. Click + Add ASIN to get started."

#### Crawler
- **Top:** Enqueue ASINs button + Retry All Failed button
- **Stats row:** 5 cards (Pending / Running / Completed / Failed / Speed)
- **Worker section:** Worker cards with status badge, current task, heartbeat time, completed count
- **Task queue:** Tabs (Failed / Pending / Running / Completed), default to Failed tab
- **Error summary bar:** Above Failed tab table — "HTTP 429: 198 · OCR failed: 32 · Empty chart: 17" — clickable to filter
- **Auto-refresh:** 10-second polling interval

#### Imports
- Import job list: filename, status (progress bar), total/added/skipped, created by, time
- Click to see details

#### Audit Log
- Filterable table: user, action, resource type, details, IP, timestamp
- Read-only view

### 6.3 Reusable Components

| Component | Usage |
|-----------|-------|
| StatsCard | Dashboard, Crawler stats |
| StatusBadge | Worker status, product status, task status |
| PriceChart | Product detail drawer (ECharts wrapper) |
| DataTable | Products, Crawler tasks, Imports, Audit — with sort, filter, pagination |
| SideDrawer | Product detail, potentially reused for task detail |
| EmptyState | All list pages when no data |
| BatchActionBar | Products, Crawler tasks — appears on selection |

### 6.4 Frontend Polling Strategy

| Page | Interval | Endpoints |
|------|----------|-----------|
| Dashboard | 30s | overview, throughput, workers, recent-failures |
| Crawler | 10s | tasks (current tab), stats, workers |
| Products | Manual refresh | — |
| Imports | 5s (while running) | import progress |

P2 upgrade: Replace polling with SSE (Server-Sent Events) for real-time worker status updates.

## 7. Logging

- **Application logs:** Continue using structlog → JSON files (not DB). Use Python `RotatingFileHandler` or system `logrotate`, retain 7 days.
- **Error aggregation (P2):** `error_events` table stores aggregated ERROR-level events (type + count + last message + timestamps). Updated by a periodic background task or on-error hook.
- **Audit logs:** All write operations logged to `audit_log` table via FastAPI middleware.

## 8. Phase Plan

### P1: Core Dashboard + Management (MVP)

- Auth (login/logout, admin_users, sessions, brute-force protection)
- Dashboard (overview stats, throughput chart, worker heartbeats, recent failures)
- Products (list, search, filter, add, import, batch ops, side drawer detail with price chart)
- Crawler (task queue with tabs, enqueue, retry, worker status)
- Imports (import job progress tracking)
- Audit log (automatic write-op logging + read view)
- Worker heartbeat mechanism
- Alembic migration: admin_users, admin_sessions, worker_heartbeats, import_jobs, audit_log

### P2: Operations Enhancement

- Runtime config (system_config table, UI editor, hot-reload in worker)
- Task scheduler (APScheduler + DB persistence, UI view + manual trigger)
- Error log viewer (error_events aggregation, filter by level/type)
- Worker control (pause/resume via DB signals)
- SSE real-time updates (replace polling for worker status)
- Log file rotation (7-day retention)
- Dashboard caching (30s in-memory TTL for high-frequency queries)

### P3: Deep Operations

- Analytics (price drop rankings, category stats, data quality reports)
- Data ops (edit/correct price data, merge duplicates, bulk modify)
- Alert center (rules, email/Telegram notifications, alert history)
- Role-based access control enforcement (admin/operator/viewer)

## 9. Dependencies

### 9.1 New Environment Variables

Add to `Settings` in `config.py`:
- `DEBUG`: bool, default `false` — controls CORS, OpenAPI docs, verbose errors
- `API_HOST`: str, default `"0.0.0.0"` — uvicorn bind host
- `API_PORT`: int, default `8000` — uvicorn bind port
- `SESSION_TTL_DAYS`: int, default `7` — admin session expiry
- `ADMIN_PASSWORD_MIN_LENGTH`: int, default `12` — minimum password length for create-user

### 9.2 Backend (add to pyproject.toml)
- `fastapi>=0.115.0`
- `uvicorn[standard]>=0.34.0`
- `bcrypt>=4.0.0`
- `python-multipart>=0.0.20` (file upload)

### 9.3 Frontend (web/package.json)
- `react`, `react-dom` (v18+)
- `vite` (v6+)
- `antd` (v5+, tree-shaking by default)
- `@ant-design/icons`
- `axios`
- `react-router-dom` (v6+)
- `echarts`, `echarts-for-react` (price charts)
- `dayjs` (date formatting, Ant Design peer dep)
- `typescript`

## 10. Wireframes

Wireframe mockups saved to `.superpowers/brainstorm/` (gitignored). Key decisions:
- Layout: Sidebar navigation
- Product detail: Side Drawer (right panel)
- Crawler: Stats cards + Worker cards + Tabbed task queue (Failed first)

## 11. Gitignore Additions

- `.superpowers/` — brainstorming session files
- `web/dist/` — frontend build output
- `data/uploads/` — import file uploads
