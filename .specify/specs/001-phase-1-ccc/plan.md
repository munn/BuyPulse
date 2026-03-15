# Implementation Plan: Phase 1 — CCC Chart Price Data Collection System

**Branch**: `001-phase-1-ccc` | **Date**: 2026-03-14 | **Spec**: spec.md

## Summary

Build a Python CLI pipeline that downloads CamelCamelCamel price chart images, extracts complete price histories via pixel analysis and OCR, stores results in PostgreSQL, and self-recovers from failures. The system is operated via `cps` CLI commands and monitored via email alerts.

## Technical Context

**Language/Version**: Python 3.12+
**Package Manager**: uv (lockfile + venv)
**Primary Dependencies**: httpx (async HTTP), Pillow (pixel analysis), pytesseract (OCR), SQLAlchemy 2.0 (async ORM), Alembic (migrations), Typer (CLI), structlog (logging), Resend (email)
**Storage**: PostgreSQL 16 (Docker Compose for local dev), PNG files on disk
**Testing**: pytest + pytest-asyncio + pytest-cov + respx (HTTP mocking), 80%+ coverage
**Target Platform**: Linux VPS (Hetzner CPX22, Ubuntu), CLI operation
**Project Type**: Single-service CLI pipeline

## Constitution Compliance

| Principle | How This Plan Aligns |
|-----------|---------------------|
| I. Compliance First | No Amazon scraping. CCC charts only. Images never shown to users. Crawler isolated from affiliate. |
| II. Respectful Crawling | Token bucket rate limiter at 1 req/s. Real httpx UA. 429 → immediate pause + cooldown. All limits configurable via env vars. |
| III. TDD | Every module gets tests first. respx for HTTP mocks. Dedicated test DB on port 5433. Sample PNGs as fixtures. |
| IV. Data Integrity | PNG saved before processing. Pixel vs OCR cross-validation (±5%). Prices in integer cents. Dedup via upsert + per-partition unique constraints. |
| V. Security | All secrets via pydantic-settings + env vars. `.env` in `.gitignore`. `.env.example` provided. SQLAlchemy ORM only (no raw SQL). uv lockfile. |
| VI. Phased Delivery | 100-ASIN pilot before scaling. Quality gates: ≥90% pass rate, ≥95% OCR accuracy. Cost < $15/month. |
| VII. Simplicity | One module = one job. Standard packages only. CLI provides clear status output. No premature optimization. |

## Project Structure

```
cps/
├── pyproject.toml
├── .env.example
├── .gitignore
├── docker-compose.yml
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── src/
│   └── cps/
│       ├── __init__.py
│       ├── config.py                # pydantic-settings
│       ├── db/
│       │   ├── __init__.py
│       │   ├── models.py            # SQLAlchemy ORM models (6 tables)
│       │   └── session.py           # async session factory
│       ├── crawler/
│       │   ├── __init__.py
│       │   ├── downloader.py        # async CCC chart download
│       │   ├── rate_limiter.py      # token bucket (1 req/s/IP)
│       │   └── storage.py           # PNG file storage by ASIN prefix
│       ├── extractor/
│       │   ├── __init__.py
│       │   ├── pixel_analyzer.py    # trace RGB curves → (date, price) series
│       │   ├── ocr_reader.py        # Tesseract: axis labels + legend text
│       │   └── calibrator.py        # pixel ↔ price/date coordinate mapping
│       ├── pipeline/
│       │   ├── __init__.py
│       │   ├── orchestrator.py      # batch processing + retry + auto-recovery
│       │   └── validator.py         # pixel vs OCR cross-validation
│       ├── seeds/
│       │   ├── __init__.py
│       │   └── manager.py           # ASIN import, dedup, priority assignment
│       ├── alerts/
│       │   ├── __init__.py
│       │   └── email.py             # Resend integration + rate limiting
│       └── cli.py                   # Typer CLI entry point
├── tests/
│   ├── conftest.py                  # shared fixtures
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_rate_limiter.py
│   │   ├── test_storage.py
│   │   ├── test_pixel_analyzer.py
│   │   ├── test_ocr_reader.py
│   │   ├── test_calibrator.py
│   │   ├── test_validator.py
│   │   └── test_seed_manager.py
│   ├── integration/
│   │   ├── test_downloader.py       # respx mocks
│   │   ├── test_db_models.py        # test PostgreSQL
│   │   ├── test_pipeline.py         # end-to-end pipeline
│   │   └── test_alerts.py           # Resend mock
│   └── fixtures/
│       ├── sample_chart_normal.png
│       ├── sample_chart_nodata.png
│       └── sample_chart_edge.png
└── data/                            # gitignored
    └── charts/
```

## Phase 0: Research

All technology decisions were finalized in session cps-2. See `research.md` for full rationale.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| HTTP client | httpx (async) | Verified working with CCC Cloudflare. `python-requests` gets 403'd. |
| Image analysis | Pillow pixel-level ops | Standard, no ML dependencies, deterministic results |
| OCR engine | Tesseract + pytesseract | Free, open-source, sufficient for chart axis/legend text |
| ORM | SQLAlchemy 2.0 async | Mature, type-safe, native async support |
| CLI framework | Typer | Modern, auto-help, minimal boilerplate |
| Alerting | Resend free tier | 3,000 emails/month, no credit card, simple API |
| Dedup strategy | Code upsert + per-partition DB unique constraints | Double safety net (decided during DB review) |

## Phase 1: Design

### Data Model

6 tables + 1 partitioning strategy. Full definitions in `data-model.md`.

Core relationships:
```
products (1) ──→ (N) price_history      partitioned by year
products (1) ──→ (3) price_summary      max 3 rows per product
products (1) ──→ (N) daily_snapshots    Phase 2 placeholder, partitioned by year
products (1) ──→ (N) extraction_runs    audit trail
products (1) ──→ (1) crawl_tasks        scheduling, in-place updates
```

Key design decisions captured during DB review:
- Prices stored as integer cents (industry standard, avoids float precision issues)
- price_history partitioned by year (7 partitions: 2020-2026)
- Dedup: dual approach — application-layer upsert + per-partition unique constraints
- crawl_tasks: one row per product (in-place update), not one row per crawl attempt
- daily_snapshots: created empty now, populated in Phase 2

### Pipeline Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│ Seed Manager │────→│  Downloader  │────→│  Extractor   │────→│ Database │
│              │     │ + Rate Limit │     │ Pixel + OCR  │     │          │
└──────────────┘     └──────┬───────┘     └──────┬───────┘     └──────────┘
                            │                    │
                       PNG Storage          Validator
                                         (pixel vs OCR)
```

Each stage is independent:
- Downloader failure → skip product, log error, continue batch
- Extractor failure → save PNG (for re-extraction later), log error, continue
- DB failure → reconnect with backoff

### Auto-Recovery State Machine

```
RUNNING ──(50 consecutive failures)──→ PAUSED
PAUSED  ──(wait 1h)──→ RECOVERING_1 (half speed)
RECOVERING_1 ──(still failing)──→ PAUSED_2
PAUSED_2 ──(wait 6h)──→ RECOVERING_2 (half speed)
RECOVERING_2 ──(still failing)──→ PAUSED_3
PAUSED_3 ──(wait 24h)──→ RECOVERING_3 (half speed)
RECOVERING_3 ──(still failing)──→ STOPPED (final alert)
RECOVERING_N ──(success)──→ RUNNING (full speed restored)
```

Each state transition sends an email alert.

### Integration Test Scenarios

Key user journeys defined in `quickstart.md`:
1. Import ASINs → verify products + crawl_tasks created
2. Crawl batch of 5 → verify PNGs saved + data extracted + DB populated
3. Re-crawl same ASIN → verify upsert (no duplicates)
4. Simulate 429 → verify rate limiter pauses and resumes
5. Simulate batch failures → verify auto-recovery state machine
6. Cross-validation → verify pixel vs OCR comparison flags low-confidence

## Phase 2: Task Planning Approach

Tasks will be generated via `/spec-kit:tasks` with the following structure:

**Task Categories:**
1. **Setup** — project scaffolding, Docker Compose, DB migrations, config
2. **Tests** — test fixtures, test files (written BEFORE implementation per TDD)
3. **Core** — implementation modules (downloader, extractor, pipeline, seeds, alerts)
4. **Integration** — end-to-end pipeline, CLI wiring
5. **Polish** — status commands, error messages, documentation

**TDD Ordering:** For each module:
- First: write test file with failing tests (RED)
- Then: write implementation to pass tests (GREEN)
- Finally: refactor if needed (REFACTOR)

**Parallel Markers:** Modules that can be developed independently:
- [P] rate_limiter, storage, config — no interdependencies
- [P] pixel_analyzer, ocr_reader — both read PNGs independently
- [S] orchestrator — depends on downloader + extractor + validator
- [S] CLI — depends on all modules

**Estimated Task Count:** ~25-30 tasks

## Complexity Tracking

No constitution deviations needed. All choices align with the 7 principles.

## Progress
- [x] Phase 0: Research
- [x] Phase 1: Design (data-model.md, quickstart.md)
- [x] Phase 2: Task planning approach described
- [x] Constitution compliance verified
