# Tasks: Phase 1 — CCC Chart Price Data Collection System

**Plan**: plan.md
**Generated**: 2026-03-14

## Phase 1: Setup

- [ ] T001 — Initialize uv project with `pyproject.toml` at project root. Configure: Python 3.12+, `src/cps` package layout, all production dependencies (httpx, pillow, pytesseract, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, typer, structlog, resend), all dev dependencies (pytest, pytest-asyncio, pytest-cov, respx). Create `src/cps/__init__.py`.
  **File**: `pyproject.toml`, `src/cps/__init__.py`

- [ ] T002 — Create Docker Compose for local development. Two PostgreSQL services: `db` on port 5432 (dev) and `db-test` on port 5433 (test). Persistent volume for dev DB. Health checks. Environment variables for credentials.
  **File**: `docker-compose.yml`

- [ ] T003 — Create pydantic-settings config module. All settings from env vars: DATABASE_URL, TEST_DATABASE_URL, CCC_BASE_URL, CCC_RATE_LIMIT (default 1.0), CCC_RETRY_MAX (default 3), CCC_BACKOFF_BASE (default 2.0), CCC_COOLDOWN_SECS (default 60), RESEND_API_KEY, ALERT_EMAIL_TO, ALERT_EMAIL_FROM, DATA_DIR (default "data"), LOG_LEVEL (default "INFO"), LOG_FORMAT (default "json"). Validate required fields at startup.
  **File**: `src/cps/config.py`

- [ ] T004 — Create `.env.example` with placeholder values for all config variables. Update `.gitignore` to include `.env`, `data/`, `__pycache__/`, `.venv/`, `*.egg-info/`, `.coverage`, `htmlcov/`.
  **File**: `.env.example`, `.gitignore`

- [ ] T005 — Create SQLAlchemy async session factory. Async engine from DATABASE_URL. Session maker with expire_on_commit=False. Context manager for session lifecycle.
  **File**: `src/cps/db/__init__.py`, `src/cps/db/session.py`

- [ ] T006 — Create SQLAlchemy ORM models for all 6 tables per data-model.md. Include: Product, ExtractionRun, PriceHistory, PriceSummary, DailySnapshot, CrawlTask. Define relationships, indexes, and constraints. PriceHistory and DailySnapshot use declarative partitioning setup.
  **File**: `src/cps/db/models.py`

- [ ] T007 — Initialize Alembic. Configure `alembic.ini` and `alembic/env.py` for async SQLAlchemy. Create initial migration that: creates all 6 tables, creates yearly partitions for price_history (2020-2026), creates partition for daily_snapshots (2026), adds per-partition unique constraints on price_history partitions `(product_id, price_type, recorded_date)`.
  **File**: `alembic.ini`, `alembic/env.py`, `alembic/versions/001_initial_schema.py`

- [ ] T008 — Create test fixtures. Shared conftest.py with: test DB session fixture (uses TEST_DATABASE_URL), auto-create/drop tables per test session, sample ASIN data factory. Create or obtain 3 sample CCC chart PNGs: `sample_chart_normal.png` (typical chart with 3 curves), `sample_chart_nodata.png` (empty/no data chart), `sample_chart_edge.png` (very low/high prices). Place in `tests/fixtures/`.
  **File**: `tests/conftest.py`, `tests/fixtures/sample_chart_*.png`

- [ ] T009 — Create all `__init__.py` files for package structure: `src/cps/db/`, `src/cps/crawler/`, `src/cps/extractor/`, `src/cps/pipeline/`, `src/cps/seeds/`, `src/cps/alerts/`. Create `tests/unit/` and `tests/integration/` directories.
  **File**: multiple `__init__.py` files

## Phase 2: Tests First (TDD)

**CRITICAL: These tests MUST be written and MUST FAIL before any implementation in Phase 3**

- [ ] T010 [P] — Write unit tests for config validation. Test: all required vars present → config loads; missing required var → ValidationError at startup; default values applied; type coercion works (string "1.0" → float).
  **File**: `tests/unit/test_config.py`

- [ ] T011 [P] — Write unit tests for rate limiter. Test: first request immediate; subsequent requests spaced ≥1s apart; 5 rapid requests take ≥4s; cooldown after 429 pauses for configured duration; configurable rate; thread safety.
  **File**: `tests/unit/test_rate_limiter.py`

- [ ] T012 [P] — Write unit tests for PNG storage. Test: saves file to correct path `data/charts/{ASIN[0:2]}/{ASIN}/{date}.png`; creates intermediate directories; handles existing file (overwrite); returns saved path; rejects invalid ASIN format.
  **File**: `tests/unit/test_storage.py`

- [ ] T013 [P] — Write unit tests for pixel analyzer using sample_chart_normal.png fixture. Test: detects at least 1 curve color (green/blue/red); returns list of (date, price_cents) tuples; handles image with no curves (sample_chart_nodata.png); handles edge case prices (sample_chart_edge.png); returns price_type label per curve.
  **File**: `tests/unit/test_pixel_analyzer.py`

- [ ] T014 [P] — Write unit tests for OCR reader using sample_chart_normal.png fixture. Test: extracts Y-axis price labels; extracts X-axis date labels; extracts legend text (lowest/highest/current with dates); returns confidence score 0.0-1.0; handles unreadable text gracefully (returns None, not crash).
  **File**: `tests/unit/test_ocr_reader.py`

- [ ] T015 [P] — Write unit tests for calibrator. Test: given Y-axis labels [(pixel_y, price_str)], builds pixel→price mapping; given X-axis labels [(pixel_x, date_str)], builds pixel→date mapping; interpolates between known points; handles reversed axes (price decreasing upward).
  **File**: `tests/unit/test_calibrator.py`

- [ ] T016 [P] — Write unit tests for validator. Test: pixel value within ±5% of OCR value → passes; pixel value >5% deviation → fails; handles missing OCR values (skip validation, flag as low_confidence); computes overall validation result from multiple price types.
  **File**: `tests/unit/test_validator.py`

- [ ] T017 [P] — Write unit tests for seed manager. Test: import from text file creates products + crawl_tasks; duplicates within file skipped; duplicates against existing DB skipped; single ASIN add works; returns import summary (total, added, skipped); assigns default priority.
  **File**: `tests/unit/test_seed_manager.py`

- [ ] T018 [P] — Write unit tests for email alerts. Test: sends email via Resend API (mocked); rate limiting: same alert type within 1 hour → only first sent; different alert types → all sent; formats subject as `[CPS Alert] {severity}: {description}`; includes stats in body.
  **File**: `tests/unit/test_alerts.py`

- [ ] T019 — Write integration test for downloader. Test with respx: successful download returns PNG bytes; HTTP 429 → raises RateLimitError; HTTP 403 → raises BlockedError; HTTP 500 → raises ServerError; timeout → raises TimeoutError; correct URL template with ASIN substitution; real httpx UA string in request headers.
  **File**: `tests/integration/test_downloader.py`

- [ ] T020 — Write integration test for DB models. Test with test PostgreSQL: create Product, verify ASIN uniqueness; create ExtractionRun linked to Product; insert PriceHistory rows, verify partition routing; upsert PriceHistory (ON CONFLICT), verify no duplicates; upsert PriceSummary, verify overwrite; create CrawlTask, verify product uniqueness; test stale task reset query.
  **File**: `tests/integration/test_db_models.py`

- [ ] T021 — Write integration test for full pipeline (quickstart.md scenarios 1-3). Test with respx + test DB: seed import → crawl batch → verify PNG saved + DB populated; re-crawl same ASIN → verify upsert dedup; verify CLI output format.
  **File**: `tests/integration/test_pipeline.py`

- [ ] T022 — Write integration test for alerts (quickstart.md scenario 10). Test: trigger alert 5 times in 10 minutes → only 1 email; wait past rate limit window → email sent again.
  **File**: `tests/integration/test_alerts.py`

## Phase 3: Core Implementation

**ONLY after Phase 2 tests are written and FAILING**

- [ ] T023 [P] — Implement rate limiter (token bucket algorithm). Configurable rate (default 1 req/s). `async acquire()` waits if needed. Cooldown mode: after 429, pause for configurable duration. Reset to normal after cooldown.
  **File**: `src/cps/crawler/rate_limiter.py`

- [ ] T024 [P] — Implement PNG storage. Save to `{DATA_DIR}/charts/{ASIN[0:2]}/{ASIN}/{YYYY-MM-DD}.png`. Create directories as needed. Return absolute path of saved file.
  **File**: `src/cps/crawler/storage.py`

- [ ] T025 [P] — Implement CCC chart downloader. Async httpx client. URL template: `https://charts.camelcamelcamel.com/us/{ASIN}/amazon-new-used.png?force=1&zero=0&w=2000&h=800&desired=false&legend=1&ilt=1&tp=all&fo=0`. Uses rate_limiter.acquire() before each request. Raises typed exceptions: RateLimitError, BlockedError, ServerError, DownloadError. Returns raw bytes on success.
  **File**: `src/cps/crawler/downloader.py`

- [ ] T026 [P] — Implement calibrator. Parse axis labels from OCR output. Build two mappings: pixel_y → price_cents (linear interpolation between Y-axis labels) and pixel_x → date (linear interpolation between X-axis labels). Handle CCC chart coordinate system (price increases upward, date increases rightward).
  **File**: `src/cps/extractor/calibrator.py`

- [ ] T027 [P] — Implement OCR reader. Use pytesseract on cropped image regions. Extract: Y-axis labels (left side crop), X-axis labels (bottom crop), legend text (top-right region). Parse price strings ("$29.99") → integer cents. Parse date strings → Python date objects. Return OCRResult dataclass with confidence score.
  **File**: `src/cps/extractor/ocr_reader.py`

- [ ] T028 [P] — Implement pixel analyzer. Load PNG with Pillow. Scan columns left-to-right within chart area. For each column, find pixels matching curve colors: green (Amazon), blue (3rd new), red (used). Use calibrator to convert pixel positions to (date, price_cents). Return dict of price_type → list of (date, price_cents) data points.
  **File**: `src/cps/extractor/pixel_analyzer.py`

- [ ] T029 — Implement validator. Compare pixel-extracted prices against OCR legend values. For each price_type: compare current, lowest, highest prices. Pass threshold: ±5%. Return ValidationResult with per-metric pass/fail and overall status (success/low_confidence/failed).
  **File**: `src/cps/pipeline/validator.py`

- [ ] T030 — Implement seed manager. Import from text file: read ASINs, validate format (10 alphanumeric chars), bulk upsert products (skip existing), create crawl_tasks for new products. Single add: same logic for one ASIN. Priority assignment based on configurable tiers. Return ImportResult summary.
  **File**: `src/cps/seeds/manager.py`

- [ ] T031 — Implement email alerts via Resend. AlertService class with send_alert(severity, title, body). Rate limiting: in-memory dict of {alert_type: last_sent_at}, skip if <1 hour. Alert types: ConsecutiveFailures, HighFailureRate, DiskUsage, StalledCrawl, QualityDrop, AutoRecoveryStatus. Format email subject/body per spec.
  **File**: `src/cps/alerts/email.py`

## Phase 4: Integration

- [ ] T032 — Implement pipeline orchestrator. Batch processing: query crawl_tasks by priority, process N at a time. Per-ASIN flow: mark in_progress → download → save PNG → extract (pixel + OCR) → validate → store results → update crawl_task. Error handling: per-ASIN try/catch, log and continue. Retry logic: exponential backoff for transient errors, skip permanent errors. Auto-recovery state machine: track consecutive failures, transition states (RUNNING→PAUSED→RECOVERING_1→PAUSED_2→RECOVERING_2→PAUSED_3→RECOVERING_3→STOPPED), send alerts on transitions. Crash recovery on startup: reset stale in_progress tasks.
  **File**: `src/cps/pipeline/orchestrator.py`

- [ ] T033 — Implement Typer CLI entry point. Commands: `cps seed import --file <path>` (bulk import ASINs), `cps seed add <ASIN>` (add single), `cps seed stats` (counts by priority tier), `cps crawl run --limit <N>` (crawl next N pending), `cps crawl status` (progress report), `cps crawl retry-failed` (reset failed tasks to pending), `cps extract run --asin <ASIN>` (re-extract from stored PNG), `cps extract batch --limit <N>` (batch re-extract), `cps db init` (run Alembic migrations), `cps db stats` (row counts, disk usage), `cps db check-partitions` (warn if current year partition missing). Configure structlog: JSON in production, colored in dev (based on LOG_FORMAT config).
  **File**: `src/cps/cli.py`

- [ ] T034 — Write integration test for auto-recovery state machine (quickstart.md scenario 7). Test with respx returning 500 for all requests: verify pause after 50 failures, verify state transitions with mocked time, verify email alerts at each transition, verify final stop after 3 rounds.
  **File**: `tests/integration/test_auto_recovery.py`

- [ ] T035 — Write integration test for crash recovery (quickstart.md scenario 8). Test: insert stale in_progress crawl_tasks (started_at = 2 hours ago), run startup recovery, verify reset to pending with retry_count preserved.
  **File**: `tests/integration/test_crash_recovery.py`

## Phase 5: Polish

- [ ] T036 [P] — Implement `cps crawl status` output. Query DB for: total products, pending/in_progress/completed/failed counts, calculate throughput (completed in last 24h), extraction quality rate (validation_passed / total extractions). Format as readable table.
  **File**: `src/cps/cli.py` (status command implementation)

- [ ] T037 [P] — Implement `cps db stats` output. Query: row counts per table, disk usage via `pg_total_relation_size()`, calculate PNG storage size from filesystem, show breakdown (OS / DB / PNGs / free), warn if >80% disk usage.
  **File**: `src/cps/cli.py` (db stats command implementation)

- [ ] T038 [P] — Implement `cps db check-partitions`. Check if partition exists for current year in both price_history and daily_snapshots. Warn with actionable message if missing. Suggest Alembic migration command.
  **File**: `src/cps/cli.py` (check-partitions command implementation)

- [ ] T039 — Run full test suite, verify 80%+ coverage. Fix any failing tests. Generate coverage report. Identify uncovered code paths and add targeted tests if below threshold.
  **File**: `pytest --cov=cps --cov-report=html`

- [ ] T040 — End-to-end pilot validation with 5 real CCC chart downloads (manual smoke test, not automated). Verify: PNGs saved correctly, pixel analysis produces reasonable data points, OCR reads axis labels, cross-validation passes, data stored in DB correctly. Document results.
  **File**: manual validation, results in pilot-report.md

## Dependencies

```
Phase 1 (Setup) → Phase 2 (Tests) → Phase 3 (Implementation) → Phase 4 (Integration) → Phase 5 (Polish)

Within phases:
- T005 (session) before T006 (models) before T007 (migrations)
- T008 (fixtures) before T013, T014 (pixel/OCR tests that use sample PNGs)
- T025 (downloader) uses T023 (rate_limiter) — but both tests can be parallel
- T028 (pixel_analyzer) uses T026 (calibrator) — but both tests can be parallel
- T029 (validator) uses T027 (ocr_reader) + T028 (pixel_analyzer) outputs
- T032 (orchestrator) depends on T023-T031 (all core modules)
- T033 (CLI) depends on T032 (orchestrator) + T030 (seeds) + T031 (alerts)
```

## Parallel Execution Guide

Tasks marked [P] within the same phase can run concurrently.
Sequential tasks (no [P]) must complete before the next starts.
Tasks in different phases are NOT parallel — complete each phase first.

| Phase | Total | Parallel [P] | Sequential |
|-------|-------|-------------|------------|
| 1. Setup | 9 | 0 | 9 |
| 2. Tests | 13 | 10 | 3 |
| 3. Core | 9 | 6 | 3 |
| 4. Integration | 4 | 0 | 4 |
| 5. Polish | 5 | 3 | 2 |
| **Total** | **40** | **19** | **21** |
