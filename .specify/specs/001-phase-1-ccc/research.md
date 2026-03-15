# Research: Technology Decisions

**Feature**: Phase 1 — CCC Chart Price Data Collection
**Date**: 2026-03-14
**Status**: All decisions finalized (session cps-2)

## 1. HTTP Client

**Decision**: httpx (async)

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| requests | Most popular, simple API | Sync only; CCC Cloudflare returns 403 for `python-requests` UA | ❌ Blocked |
| httpx | Async + sync, modern API, passes CCC Cloudflare | Slightly newer than requests | ✅ Chosen |
| aiohttp | Battle-tested async | More verbose API, less ergonomic | ❌ httpx preferred |

Key finding: CCC Cloudflare filters by User-Agent. `python-requests` → 403. `httpx` → 200.

## 2. Image Analysis

**Decision**: Pillow (PIL)

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Pillow | Standard, pixel-level access, no ML deps | Manual curve tracing logic needed | ✅ Chosen |
| OpenCV | Powerful image processing | Heavy dependency, overkill for RGB tracing | ❌ Overkill |
| matplotlib image reading | Built into data science stack | Not designed for pixel analysis | ❌ Wrong tool |

Approach: Load PNG → scan columns → detect curve colors (green=Amazon, blue=3rd new, red=used) → map pixel positions to price/date via axis calibration.

## 3. OCR Engine

**Decision**: Tesseract + pytesseract

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Tesseract | Free, open-source, good for structured text | Requires system install | ✅ Chosen |
| EasyOCR | Python-native, deep learning | Heavy GPU deps, slower | ❌ Overkill |
| Google Vision API | Best accuracy | Paid, network dependency | ❌ Cost |
| PaddleOCR | Good accuracy, free | Complex install | ❌ Complexity |

Tesseract is sufficient for chart text (axis labels, legend values) — structured, consistent font, high contrast.

## 4. Database ORM

**Decision**: SQLAlchemy 2.0 (async)

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| SQLAlchemy 2.0 | Mature, async, type-safe, Alembic migrations | Learning curve | ✅ Chosen |
| Tortoise ORM | Django-like, async-native | Less mature, smaller community | ❌ Maturity |
| Raw asyncpg | Maximum performance | No ORM, manual SQL | ❌ Constitution V (security) |
| Django ORM | Very mature | Pulls in entire Django framework | ❌ Overkill |

## 5. CLI Framework

**Decision**: Typer

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Typer | Modern, auto-help, type hints | Depends on click | ✅ Chosen |
| Click | Battle-tested, flexible | More boilerplate | ❌ Typer wraps it better |
| argparse | Standard library | Verbose, no auto-help | ❌ Too verbose |

## 6. Email Alerting

**Decision**: Resend (free tier)

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Resend | 3,000/month free, no credit card, simple API | Newer service | ✅ Chosen |
| SendGrid | 100/day free, mature | Needs credit card for signup | ❌ Credit card |
| AWS SES | Cheap at scale | AWS account + verification required | ❌ Setup complexity |
| SMTP direct | No third party | Deliverability issues, spam filters | ❌ Unreliable |

## 7. Deduplication Strategy

**Decision**: Dual approach — application upsert + per-partition unique constraints

Decided during database review session. Application layer uses `INSERT ... ON CONFLICT DO UPDATE` for all writes. Additionally, each yearly partition gets a unique constraint on `(product_id, price_type, recorded_date)` as a safety net.

## 8. Configuration Management

**Decision**: pydantic-settings

Validates all environment variables at startup with type safety. Fails fast with clear error if required config is missing. Supports `.env` files for local development.

## 9. Logging

**Decision**: structlog

Produces structured JSON logs in production (parseable by log aggregation tools). Human-readable colored output in development. Both modes via single config toggle.

## 10. Testing Stack

**Decision**: pytest + pytest-asyncio + pytest-cov + respx

- pytest: Standard Python test runner
- pytest-asyncio: Test async code
- pytest-cov: Coverage reporting (80%+ target)
- respx: Mock httpx requests (matches our HTTP client)
