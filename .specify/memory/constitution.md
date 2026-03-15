# CPS Project Constitution

## Core Principles

### I. Compliance First — Amazon Associates Rules Are Non-Negotiable

- Crawler infrastructure and affiliate account MUST be fully isolated (different IPs, domains, identities)
- NEVER scrape Amazon.com directly — this violates the Associates Operating Agreement and results in account termination
- Creators API price data MUST NOT be cached beyond 24 hours
- CCC chart images MUST NOT be displayed to end users — only self-built data and visualizations are permitted
- Any new data source MUST be reviewed for Associates compliance before integration

### II. Respectful Crawling — Be a Good Neighbor

- Request rate MUST NOT exceed 1 request/second per IP against any single target
- HTTP client MUST use its real User-Agent string (e.g., `httpx/0.x`) — never impersonate a browser
- If a target returns 429 or asks to stop, crawling MUST pause immediately and respect the cooldown
- All crawl behavior MUST be configurable via environment variables (rate limits, retry counts, backoff durations) so it can be tuned without code changes

### III. Test-Driven Development — Tests Before Implementation

- Every module MUST have tests written before the implementation code (RED → GREEN → REFACTOR)
- Test coverage target: 80%+ across the codebase
- Tests MUST be runnable in isolation — no dependency on external services (CCC, Amazon) during test execution
- HTTP interactions in tests MUST use `respx` mocks with realistic fixtures (sample PNGs, response headers)
- Integration tests MUST run against a dedicated test PostgreSQL instance (Docker Compose, port 5433)

### IV. Data Integrity — Store Raw, Validate Cross-Layer

- Original CCC chart PNGs MUST be saved to disk before any processing — they are the source of truth and enable re-extraction
- Every pixel-analysis extraction MUST be cross-validated against OCR legend values (±5% tolerance)
- Extraction results that fail validation MUST be stored (with `validation_passed = false`) but excluded from user-facing queries
- Prices MUST be stored as integers in cents — never as floats
- Deduplication MUST be enforced at the application layer via upsert (INSERT ... ON CONFLICT DO UPDATE)

### V. Security by Default — No Shortcuts

- No secrets (API keys, database passwords, email credentials) in source code — all via environment variables validated by pydantic-settings at startup
- `.env` MUST be in `.gitignore`; `.env.example` with placeholder values MUST exist for documentation
- PostgreSQL MUST listen on localhost only — no remote access
- All SQL queries MUST go through SQLAlchemy ORM (parameterized) — no raw string interpolation
- Dependencies MUST be pinned via uv lockfile

### VI. Phased Delivery — Ship Small, Validate Early

- Phase 1 (data collection) MUST be fully operational before starting Phase 2 (Telegram Bot)
- Each phase starts with a 100-ASIN pilot to validate the pipeline end-to-end before scaling
- Scaling thresholds MUST be defined and monitored: disk usage, extraction quality rate, crawl success rate
- New features MUST NOT break existing pipeline stages — each stage (download → extract → store) is independently deployable and testable
- Cost MUST stay under $15/month for Phase 1 infrastructure

### VII. Simplicity Over Cleverness — One Person Team

- The codebase MUST be understandable by a single developer returning after a month away
- Prefer standard library and well-known packages over novel abstractions
- Each Python module MUST have a single clear responsibility (downloader downloads, extractor extracts, etc.)
- No premature optimization: solve for 500K ASINs, not 50M — upgrade path documented but not built until needed
- CLI commands (`cps crawl`, `cps seed`, `cps extract`) MUST provide clear status output so operations are observable without reading logs

## Governance

- This constitution supersedes ad-hoc decisions during development.
- Amendments require: (1) documented rationale, (2) version bump, (3) update to Last Amended date.
- All specs, plans, and tasks must be checked against these principles.
- When a principle proves wrong in practice, amend it — don't silently ignore it.

**Version**: 1.0.0 | **Ratified**: 2026-03-14 | **Last Amended**: 2026-03-14
