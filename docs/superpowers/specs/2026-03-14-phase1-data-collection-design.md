# Phase 1: Data Collection System Design

> Date: 2026-03-14
> Status: Approved
> Scope: CCC chart download, pixel analysis, OCR extraction, database, ASIN seed management

### 决策原则

所有技术决策必须向用户解释清楚：列出选项、优缺点、推荐理由和对未来的影响。用通俗语言，不甩术语。最终由用户拍板，不可擅自替用户做决定。

---

## 1. System Architecture

Pipeline architecture with four independent stages:

```
ASIN Seed Manager → CCC Chart Downloader → Price Extractor → PostgreSQL
                         ↓
                    PNG File Storage
```

Each stage is decoupled: failures in one stage do not cascade. Future data sources (Creators API, RSS feeds, user queries) plug into the same pipeline.

### CCC Chart URL Template

```
https://charts.camelcamelcamel.com/us/{ASIN}/amazon-new-used.png?force=1&zero=0&w=2000&h=800&desired=false&legend=1&ilt=1&tp=all&fo=0
```

Key parameters:
- `w=2000&h=800`: high resolution for accurate pixel analysis (actual return is ~2x)
- `tp=all`: full price history (not 3m/6m/1y)
- `legend=1`: include legend with min/max/current prices for validation
- `amazon-new-used`: all three price curves in one image

### Data Flow

```
1. crawl_tasks table provides next ASIN batch (priority-ordered)
2. Downloader fetches chart PNG from charts.camelcamelcamel.com
3. PNG saved to disk (organized by ASIN prefix)
4. Extractor runs pixel analysis:
   a. OCR X-axis labels → pixel-to-date mapping
   b. OCR Y-axis labels → pixel-to-price mapping
   c. Trace curve colors (green/blue/red) column-by-column → (date, price) series
5. Extractor runs legend OCR → lowest/highest/current prices (validation)
6. Results written to price_history + price_summary tables
7. crawl_tasks updated with completion status and next scheduled time
```

---

## 2. Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.12+ | Best ecosystem for image processing, OCR, async HTTP |
| Package manager | uv | Fastest, modern lockfile + venv management |
| HTTP client | httpx (async) | Verified working with CCC Cloudflare; async for throughput |
| Image analysis | Pillow (PIL) | Standard library for pixel-level operations |
| OCR | Tesseract + pytesseract | Free, open-source, sufficient for chart text |
| Database ORM | SQLAlchemy 2.0 | Mature, async support, type-safe queries |
| Migrations | Alembic | Schema versioning, rollback support |
| Configuration | pydantic-settings | Env var validation, type safety, .env file support |
| CLI | Typer | Modern Python CLI with auto-generated help |
| Local dev DB | Docker Compose | One-command PostgreSQL for development |
| Logging | structlog | Structured JSON logging for production |
| Email alerts | Resend (free tier) | System alerts: failures, disk usage, stalled crawls |
| Testing | pytest + pytest-asyncio + pytest-cov | TDD workflow, 80%+ coverage target |
| HTTP mocking | respx | Mock CCC requests in tests without real network calls |

---

## 3. Database Schema

### 3.1 `products`

Core product catalog. One row per ASIN.

```sql
CREATE TABLE products (
    id          BIGSERIAL PRIMARY KEY,
    asin        VARCHAR(10) NOT NULL,
    title       TEXT,
    category    VARCHAR(255),
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_products_asin UNIQUE (asin)
);

CREATE INDEX idx_products_category ON products(category);
```

Note: `image_dir` removed — PNG path is deterministic from ASIN (`data/charts/{ASIN[0:2]}/{ASIN}/`).

### 3.2 `extraction_runs`

Metadata for each extraction attempt. Tracks provenance, quality metrics, and errors.
One row per extraction attempt (a product can have multiple runs over time).

```sql
CREATE TABLE extraction_runs (
    id              BIGSERIAL PRIMARY KEY,
    product_id      BIGINT NOT NULL REFERENCES products(id),
    chart_path      VARCHAR(500) NOT NULL,  -- path to source PNG
    status          VARCHAR(20) NOT NULL,   -- 'success', 'failed', 'low_confidence'
    points_extracted INTEGER,               -- number of price data points found
    ocr_confidence  REAL,                   -- 0.0-1.0 overall OCR confidence
    validation_passed BOOLEAN,             -- pixel vs OCR cross-check result
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_er_product ON extraction_runs(product_id);
CREATE INDEX idx_er_status ON extraction_runs(status);
```

### 3.3 `price_history`

Complete price time series extracted from CCC charts. Every inflection point on the curve becomes one row. Expected scale: 100M+ rows at full capacity.

```sql
CREATE TABLE price_history (
    id              BIGSERIAL,
    product_id      BIGINT NOT NULL REFERENCES products(id),
    price_type      VARCHAR(20) NOT NULL,  -- 'amazon', 'new', 'used'
    recorded_date   DATE NOT NULL,
    price_cents     INTEGER NOT NULL,      -- price in cents to avoid float issues
    source          VARCHAR(20) NOT NULL DEFAULT 'ccc_chart',
    extraction_id   BIGINT REFERENCES extraction_runs(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id, recorded_date)
) PARTITION BY RANGE (recorded_date);

-- Deduplication: upsert via ON CONFLICT on (product_id, price_type, recorded_date)
-- Enforced at application layer since partitioned tables have limited unique constraint support.
-- Application uses: INSERT ... ON CONFLICT (product_id, price_type, recorded_date) DO UPDATE

-- Yearly partitions. New partitions added via Alembic migration each December.
CREATE TABLE price_history_2020 PARTITION OF price_history
    FOR VALUES FROM ('2020-01-01') TO ('2021-01-01');
CREATE TABLE price_history_2021 PARTITION OF price_history
    FOR VALUES FROM ('2021-01-01') TO ('2022-01-01');
CREATE TABLE price_history_2022 PARTITION OF price_history
    FOR VALUES FROM ('2022-01-01') TO ('2023-01-01');
CREATE TABLE price_history_2023 PARTITION OF price_history
    FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
CREATE TABLE price_history_2024 PARTITION OF price_history
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE price_history_2025 PARTITION OF price_history
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE price_history_2026 PARTITION OF price_history
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

-- Unique constraint per partition for dedup (applied to each partition)
-- ALTER TABLE price_history_20XX ADD CONSTRAINT uq_ph_20XX
--     UNIQUE (product_id, price_type, recorded_date);

CREATE INDEX idx_ph_product_date ON price_history(product_id, recorded_date);
CREATE INDEX idx_ph_product_type ON price_history(product_id, price_type);
```

### 3.4 `price_summary`

OCR-extracted legend values. Used for quick lookups and validation against pixel analysis.
Re-crawling the same ASIN overwrites the previous summary (upsert via `ON CONFLICT DO UPDATE`).

```sql
CREATE TABLE price_summary (
    id              BIGSERIAL PRIMARY KEY,
    product_id      BIGINT NOT NULL REFERENCES products(id),
    price_type      VARCHAR(20) NOT NULL,  -- 'amazon', 'new', 'used'
    lowest_price    INTEGER,               -- cents
    lowest_date     DATE,
    highest_price   INTEGER,               -- cents
    highest_date    DATE,
    current_price   INTEGER,               -- cents
    current_date    DATE,
    source          VARCHAR(20) NOT NULL DEFAULT 'ccc_legend',
    extraction_id   BIGINT REFERENCES extraction_runs(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(product_id, price_type)
);
```

### 3.5 `daily_snapshots` *(Phase 2)*

Phase 2+ self-built price accumulation via Creators API. Table created now but remains empty until Phase 2.

```sql
CREATE TABLE daily_snapshots (
    id              BIGSERIAL,
    product_id      BIGINT NOT NULL REFERENCES products(id),
    snapshot_date   DATE NOT NULL,
    price_cents     INTEGER NOT NULL,
    source          VARCHAR(20) NOT NULL DEFAULT 'creators_api',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (id, snapshot_date)
) PARTITION BY RANGE (snapshot_date);

CREATE TABLE daily_snapshots_2026 PARTITION OF daily_snapshots
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE INDEX idx_ds_product_date ON daily_snapshots(product_id, snapshot_date);
```

### 3.7 `crawl_tasks`

Crawl scheduling and state management. Drives the pipeline.
One row per product (updated in-place for re-crawl cycles). Intentionally no crawl history —
historical extraction metadata is tracked in `extraction_runs`.

On startup, stale `in_progress` tasks (started_at > 1 hour ago) are reset to `pending` for graceful recovery.

```sql
CREATE TABLE crawl_tasks (
    id              BIGSERIAL PRIMARY KEY,
    product_id      BIGINT NOT NULL REFERENCES products(id),
    priority        SMALLINT NOT NULL DEFAULT 5,    -- 1=highest, 10=lowest
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
                    -- pending, in_progress, completed, failed, skipped
    scheduled_at    TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    retry_count     SMALLINT NOT NULL DEFAULT 0,
    max_retries     SMALLINT NOT NULL DEFAULT 3,
    error_message   TEXT,
    next_crawl_at   TIMESTAMPTZ,        -- when to re-crawl
    total_crawls    INTEGER NOT NULL DEFAULT 0,  -- lifetime crawl count
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(product_id)
);

CREATE INDEX idx_ct_status_priority ON crawl_tasks(status, priority, scheduled_at);
CREATE INDEX idx_ct_next_crawl ON crawl_tasks(next_crawl_at) WHERE status = 'completed';
```

### Update Schedule Logic

| Tier | ASIN Count | Crawl Frequency | Priority |
|------|-----------|-----------------|----------|
| Hot (Top 10K) | 10,000 | Daily | 1 |
| Standard (10K-100K) | 90,000 | Weekly | 5 |
| Long tail (100K+) | 400,000+ | On-demand | 9 |

---

## 4. Project Structure

```
cps/
├── pyproject.toml                  # uv project config + dependencies
├── .env.example                    # env var template (no real secrets)
├── .gitignore                      # .env, data/, __pycache__, etc.
├── docker-compose.yml              # local dev PostgreSQL + test PostgreSQL
├── alembic.ini                     # migration config
├── src/
│   └── cps/
│       ├── __init__.py
│       ├── config.py               # pydantic-settings: all config from env vars
│       ├── db/
│       │   ├── __init__.py
│       │   ├── models.py           # SQLAlchemy ORM models
│       │   ├── session.py          # async DB session factory
│       │   └── migrations/
│       │       └── versions/       # Alembic migration files
│       ├── crawler/
│       │   ├── __init__.py
│       │   ├── downloader.py       # async CCC chart HTTP downloader
│       │   ├── rate_limiter.py     # token bucket rate limiter (1 req/s/IP)
│       │   └── storage.py          # PNG file storage (organized by ASIN prefix)
│       ├── extractor/
│       │   ├── __init__.py
│       │   ├── pixel_analyzer.py   # trace curve colors → (date, price) series
│       │   ├── ocr_reader.py       # Tesseract OCR for legend/axis text
│       │   └── calibrator.py       # map pixel coordinates ↔ price/date values
│       ├── seeds/
│       │   ├── __init__.py
│       │   └── manager.py          # ASIN seed import, dedup, priority assignment
│       ├── alerts/
│       │   ├── __init__.py
│       │   └── email.py            # Resend email alerts (failures, disk, stalls)
│       └── cli.py                  # Typer CLI: crawl, extract, seed, status
├── tests/
│   ├── conftest.py                 # shared fixtures: test DB, sample data
│   ├── unit/
│   │   ├── test_pixel_analyzer.py  # pixel analysis with sample PNGs
│   │   ├── test_ocr_reader.py      # OCR with sample PNGs
│   │   ├── test_calibrator.py      # axis calibration logic
│   │   ├── test_rate_limiter.py    # rate limiting behavior
│   │   └── test_config.py          # config validation
│   ├── integration/
│   │   ├── test_downloader.py      # HTTP mocking with respx
│   │   ├── test_db_models.py       # DB operations with test PostgreSQL
│   │   └── test_pipeline.py        # end-to-end: download → extract → store
│   └── fixtures/
│       ├── sample_chart_normal.png  # typical chart for happy-path tests
│       ├── sample_chart_nodata.png  # chart with missing data
│       └── sample_chart_edge.png   # edge case: very low/high prices
└── data/                           # local data dir (gitignored)
    └── charts/                     # downloaded PNGs organized by ASIN prefix
        └── B0/
            └── B00001234/
                └── 2026-03-14.png
```

### PNG Storage Convention

Files organized by first 2 chars of ASIN to avoid single-directory file limits:

```
data/charts/{ASIN[0:2]}/{ASIN}/{YYYY-MM-DD}.png
```

At 500K ASINs, each prefix bucket holds ~1,400 dirs (manageable for any filesystem).

---

## 5. Security Design

### 5.1 Code-Level Security

- **No secrets in code**: all credentials via environment variables, validated by pydantic-settings at startup
- **`.env` in `.gitignore`**: prevents accidental commit of secrets
- **`.env.example`** with placeholder values: documents required variables without exposing real ones
- **Parameterized SQL**: SQLAlchemy ORM prevents SQL injection
- **Dependency pinning**: uv lockfile ensures reproducible, auditable dependencies

### 5.2 VPS Security (deployment checklist)

- [ ] SSH key-only authentication (disable password login)
- [ ] fail2ban installed and active (auto-ban brute force IPs)
- [ ] UFW firewall: allow SSH (22) only, deny all else
- [ ] PostgreSQL listens on localhost only (no remote access)
- [ ] PostgreSQL strong password (generated, 32+ chars)
- [ ] Automatic security updates enabled (unattended-upgrades)
- [ ] Non-root user for application (dedicated `cps` user)
- [ ] Log monitoring: crawl errors, auth failures, disk usage

### 5.3 Crawl/Affiliate Isolation

- Crawler runs on Hetzner VPS (dedicated IP)
- Affiliate account operates from separate infrastructure
- No shared cookies, sessions, or identifiers between the two

---

## 6. ASIN Seed Sources

### Source 1: Curated ASIN Lists (primary)

Initial seed from publicly available ASIN datasets and lists:
- Amazon Best Sellers category URLs → extract ASINs from page (public, no login required)
- Open datasets on Kaggle/GitHub with Amazon product ASINs
- Manually curated CSV files for high-priority categories

~3,000-30,000 ASINs as starting seed depending on category depth.
Implementation: import from CSV/text files via `cps seed import`.

### Source 2: CCC Top Drops RSS

`https://camelcamelcamel.com/top_drops/feed` — structured XML feed of trending price drops.
Low volume (~20/day) but high-value signal for deal detection.

### Source 3: User Query Expansion (Phase 2)

When Telegram Bot users query a product, auto-add its ASIN to the seed database.
Organic growth driven by actual user demand.

### Seed Import Flow

```
Raw ASIN list → Dedup against products table → Insert new products → Create crawl_tasks
```

---

## 7. CLI Commands

```bash
# Seed management
cps seed import --file asins.txt       # import ASIN list
cps seed add B00XYZ1234               # add single ASIN
cps seed stats                         # show seed counts by priority

# Crawling
cps crawl run --limit 100             # crawl next 100 pending tasks
cps crawl status                       # show crawl progress
cps crawl retry-failed                 # retry failed tasks

# Extraction (if running separately from crawl)
cps extract run --asin B00XYZ1234     # extract from stored PNG
cps extract batch --limit 100         # batch extract pending

# Database
cps db init                            # run migrations
cps db stats                           # table row counts, disk usage
```

---

## 8. Error Handling

| Error | Response | Retry? |
|-------|----------|--------|
| HTTP 429 (rate limited) | Wait 60s, then resume at reduced rate | Yes, after backoff |
| HTTP 403 (blocked) | Log, skip ASIN, alert if >10% fail rate | No |
| HTTP 5xx | Retry with exponential backoff | Yes, max 3 |
| Network timeout | Retry once | Yes, max 1 |
| OCR extraction fails | Save PNG, mark for manual review | No auto-retry |
| Pixel analysis anomaly | Cross-validate with OCR legend values | Flag if >10% deviation |
| DB connection lost | Reconnect with backoff | Yes |

---

## 9. Validation & Accuracy Targets

### Pixel Analysis Validation

Each extraction run is cross-validated against OCR legend values:

| Metric | Pass Threshold | Action on Fail |
|--------|---------------|----------------|
| Current price: pixel vs OCR | Within ±5% | Flag as `low_confidence` in extraction_runs |
| Lowest price: pixel vs OCR | Within ±5% | Flag as `low_confidence` |
| Highest price: pixel vs OCR | Within ±5% | Flag as `low_confidence` |
| Number of curves detected | ≥1 (out of 3 possible) | Mark `failed` if 0 curves found |
| OCR confidence score | ≥0.7 | Flag for manual review if below |

Flagged data is still stored (with `validation_passed = false`) but excluded from user-facing queries until reviewed.

### Pipeline Readiness Criteria

Before scaling beyond 100 ASINs:
- ≥90% of test ASINs must pass validation (current price within ±5% of OCR)
- OCR must correctly read axis labels on ≥95% of charts
- No systematic bias (pixel analysis not consistently over/under-estimating)

---

## 10. Disk Space & Storage Planning

### Budget (Hetzner CPX22: 40GB SSD)

| Component | Allocation | Notes |
|-----------|-----------|-------|
| OS + packages | ~4 GB | Ubuntu + Python + Tesseract |
| PostgreSQL data | ~6 GB | 500K products, 50M price_history rows |
| PNG storage | ~25 GB | 500K ASINs × ~50KB each |
| Buffer | ~5 GB | WAL, temp files, headroom |

### Scale Thresholds

| ASIN Count | PNG Storage | Action |
|-----------|-------------|--------|
| < 100K | < 5 GB | No concern |
| 100K-400K | 5-25 GB | Monitor weekly |
| > 400K | > 25 GB | Upgrade to CPX32 (80GB) or add volume storage |
| > 1M | > 50 GB | Move PNGs to Hetzner Object Storage (~€5/TB/mo) |

### Monitoring

`cps db stats` command reports:
- Disk usage breakdown (OS / DB / PNGs / free)
- Alert at 80% disk usage
- Row counts per table
- Crawl throughput (ASINs/day, success rate)
- Extraction quality (% passing validation)

---

## 11. Operational Notes

### Tesseract Installation

Required on both local dev and VPS:
```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr tesseract-ocr-eng

# macOS (local dev)
brew install tesseract
```

Docker Compose for local dev includes Tesseract in the app container.

### Graceful Shutdown

On startup, the crawler resets stale `in_progress` tasks:
```sql
UPDATE crawl_tasks SET status = 'pending', retry_count = retry_count
WHERE status = 'in_progress' AND started_at < NOW() - INTERVAL '1 hour';
```

### Partition Maintenance

New yearly partitions are added via Alembic migration each December.
A `cps db check-partitions` command warns if the current year's partition is missing.

---

## 12. Email Alerting

System sends email alerts for critical events. Uses Resend free tier (3,000 emails/month, no credit card).

### Alert Triggers

| Trigger | Condition | Severity |
|---------|-----------|----------|
| Consecutive failures | >50 ASINs fail in a row | CRITICAL — auto-pauses crawl |
| High failure rate | >10% of batch fails | WARNING |
| Disk usage | >80% of VPS disk | CRITICAL |
| Stalled crawl | No progress for >24 hours | WARNING |
| Extraction quality drop | Validation pass rate <80% | WARNING |

### Alert Email Format

Subject: `[CPS Alert] {severity}: {brief description}`
Body: what happened, current stats, suggested action.

### Implementation

- `src/cps/alerts/email.py` — Resend API integration
- Alerts are rate-limited (max 1 email per alert type per hour) to avoid inbox flooding
- Alert config (recipient email, thresholds) via environment variables

---

## 13. Future Extension Points

- **New data sources**: add new crawler modules (e.g., `crawler/keepa.py`, `crawler/creators_api.py`)
- **Telegram Bot** (Phase 2): reads from price_history/daily_snapshots, writes user queries to seeds
- **Multi-region**: add `region` column to products/price_history (currently US-only)
- **Proxy support**: rate_limiter.py already supports multi-IP; add proxy pool configuration
- **Monitoring**: structlog JSON output ready for log aggregation (Loki, ELK, etc.)
