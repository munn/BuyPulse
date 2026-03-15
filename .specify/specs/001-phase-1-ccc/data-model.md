# Data Model: Phase 1 — CCC Chart Price Data Collection

**Date**: 2026-03-14

## Entity Relationship Overview

```
products (1) ──→ (N) price_history       [partitioned by year, 100M+ rows]
products (1) ──→ (3) price_summary       [max 3 per product, upsert]
products (1) ──→ (N) daily_snapshots     [Phase 2, partitioned by year]
products (1) ──→ (N) extraction_runs     [audit trail]
products (1) ──→ (1) crawl_tasks         [in-place update scheduling]
```

## Table Definitions

### 1. products

Core product catalog. One row per ASIN.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Internal ID |
| asin | VARCHAR(10) | NOT NULL, UNIQUE | Amazon product identifier |
| title | TEXT | nullable | Product name (populated in Phase 2) |
| category | VARCHAR(255) | nullable | Product category (populated in Phase 2) |
| first_seen | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | When added to system |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Last modification |

Indexes: `idx_products_category ON (category)`

Scale: ~500K rows.

### 2. extraction_runs

One row per extraction attempt. Tracks provenance, quality, and errors.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Run ID |
| product_id | BIGINT | NOT NULL, FK → products(id) | Which product |
| chart_path | VARCHAR(500) | NOT NULL | Path to source PNG |
| status | VARCHAR(20) | NOT NULL | 'success', 'failed', 'low_confidence' |
| points_extracted | INTEGER | nullable | Number of data points found |
| ocr_confidence | REAL | nullable | 0.0-1.0 OCR confidence |
| validation_passed | BOOLEAN | nullable | Pixel vs OCR cross-check |
| error_message | TEXT | nullable | Error details if failed |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | When extraction ran |

Indexes: `idx_er_product ON (product_id)`, `idx_er_status ON (status)`

### 3. price_history ⭐ (core table)

Complete price time series. Every inflection point = one row.
**Partitioned by year** (RANGE on recorded_date).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | part of composite PK | Row ID |
| product_id | BIGINT | NOT NULL, FK → products(id) | Which product |
| price_type | VARCHAR(20) | NOT NULL | 'amazon', 'new', 'used' |
| recorded_date | DATE | NOT NULL | Date of this price point |
| price_cents | INTEGER | NOT NULL | Price in cents ($29.99 = 2999) |
| source | VARCHAR(20) | NOT NULL, DEFAULT 'ccc_chart' | Data origin |
| extraction_id | BIGINT | FK → extraction_runs(id) | Provenance |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Insert timestamp |

Primary key: `(id, recorded_date)` — composite required for partitioning.

Partitions: `price_history_2020` through `price_history_2026` (yearly).

**Per-partition unique constraint**: `UNIQUE (product_id, price_type, recorded_date)` on each partition — prevents duplicate data even if application code has bugs.

Indexes: `idx_ph_product_date ON (product_id, recorded_date)`, `idx_ph_product_type ON (product_id, price_type)`

Scale: 100M+ rows at full capacity.

### 4. price_summary

OCR-extracted legend values. Quick lookup + validation cache.
Upsert on `(product_id, price_type)` — re-crawl overwrites previous values.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Row ID |
| product_id | BIGINT | NOT NULL, FK → products(id) | Which product |
| price_type | VARCHAR(20) | NOT NULL | 'amazon', 'new', 'used' |
| lowest_price | INTEGER | nullable | Historical lowest (cents) |
| lowest_date | DATE | nullable | Date of lowest |
| highest_price | INTEGER | nullable | Historical highest (cents) |
| highest_date | DATE | nullable | Date of highest |
| current_price | INTEGER | nullable | Current price (cents) |
| current_date | DATE | nullable | Date of current |
| source | VARCHAR(20) | NOT NULL, DEFAULT 'ccc_legend' | Data origin |
| extraction_id | BIGINT | FK → extraction_runs(id) | Provenance |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Insert timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Last update |

Unique constraint: `UNIQUE (product_id, price_type)`

Scale: max ~1.5M rows (500K products × 3 price types).

### 5. daily_snapshots (Phase 2 placeholder)

Self-built daily price records via Creators API. Created empty now.
**Partitioned by year** (same pattern as price_history).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | part of composite PK | Row ID |
| product_id | BIGINT | NOT NULL, FK → products(id) | Which product |
| snapshot_date | DATE | NOT NULL | Snapshot date |
| price_cents | INTEGER | NOT NULL | Price in cents |
| source | VARCHAR(20) | NOT NULL, DEFAULT 'creators_api' | Data origin |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Insert timestamp |

Primary key: `(id, snapshot_date)` — composite for partitioning.

Partitions: `daily_snapshots_2026` (one partition for now, add yearly).

Index: `idx_ds_product_date ON (product_id, snapshot_date)`

### 6. crawl_tasks

Crawl scheduling. One row per product, updated in-place.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | BIGSERIAL | PRIMARY KEY | Task ID |
| product_id | BIGINT | NOT NULL, FK → products(id), UNIQUE | Which product |
| priority | SMALLINT | NOT NULL, DEFAULT 5 | 1=highest, 10=lowest |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'pending' | pending/in_progress/completed/failed/skipped |
| scheduled_at | TIMESTAMPTZ | nullable | Planned start time |
| started_at | TIMESTAMPTZ | nullable | Actual start time |
| completed_at | TIMESTAMPTZ | nullable | Completion time |
| retry_count | SMALLINT | NOT NULL, DEFAULT 0 | Current retry count |
| max_retries | SMALLINT | NOT NULL, DEFAULT 3 | Max retries allowed |
| error_message | TEXT | nullable | Last error |
| next_crawl_at | TIMESTAMPTZ | nullable | Next re-crawl time |
| total_crawls | INTEGER | NOT NULL, DEFAULT 0 | Lifetime crawl count |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Creation time |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | Last update |

Indexes: `idx_ct_status_priority ON (status, priority, scheduled_at)`, `idx_ct_next_crawl ON (next_crawl_at) WHERE status = 'completed'`

Scale: ~500K rows (one per product).

## Design Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Price storage | Integer cents | Avoids floating-point precision issues. Industry standard. |
| price_history partitioning | Yearly RANGE on recorded_date | Query optimization for time-range queries. Easy old-data cleanup. |
| Dedup enforcement | App upsert + per-partition UNIQUE | Double safety net. DB constraint catches app bugs. |
| crawl_tasks cardinality | 1 row per product (in-place update) | Keeps table small. History lives in extraction_runs. |
| daily_snapshots timing | Create table now, populate Phase 2 | Avoids schema migration during Phase 2 launch. |
| Variation/parent_asin | Not added in Phase 1 | No data source for it. Easy to add via migration in Phase 2. |

## Partition Maintenance

New yearly partitions added via Alembic migration each December.
A `cps db check-partitions` CLI command warns if current year's partition is missing.

## Crash Recovery

On startup: reset stale `in_progress` crawl_tasks (started > 1 hour ago) to `pending`.
