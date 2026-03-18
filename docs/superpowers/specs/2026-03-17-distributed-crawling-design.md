# Distributed Multi-Platform Crawling Architecture

> Date: 2026-03-17
> Status: Approved (v3)
> Scope: CPS crawler evolution from single-platform monolith to distributed multi-platform system

## 1. Problem Statement

Current system: ~8K ASINs from CCC top_drops only, single-process serial crawling, Amazon-only.

Target: millions of products across Amazon, Best Buy, Walmart (and more), with distributed workers and phased deployment.

Key constraint: user needs sufficient product coverage for Telegram Bot to provide useful results. 50K products is too thin — users searching for random products will get no results.

## 2. Architecture Overview

```
                    ┌─────────────────┐
                    │   Task Queue    │  ← TaskQueue Protocol
                    │  (DB polling →  │     (swap to Redis later)
                    │   Redis later)  │
                    └────────┬────────┘
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ Worker 1 │  │ Worker 2 │  │ Worker N │
        │ Amazon   │  │ Amazon   │  │ BestBuy  │
        │ (proxy-A)│  │ (proxy-B)│  │ (no prx) │
        └────┬─────┘  └────┬─────┘  └────┬─────┘
             └──────────────┼─────────────┘
                            ▼
                    ┌─────────────┐
                    │ PostgreSQL  │  ← Unified data model
                    └─────────────┘
```

## 3. Design Decisions

### 3.1 Unified Data Model

**Decision**: Rename `asin` → `platform_id`, add `platform` field.

```sql
-- Products table
ALTER TABLE products ADD COLUMN platform VARCHAR(30) DEFAULT 'amazon';
ALTER TABLE products RENAME COLUMN asin TO platform_id;
ALTER TABLE products ALTER COLUMN platform_id TYPE VARCHAR(30);  -- accommodate all platform ID lengths
ALTER TABLE products ADD COLUMN url TEXT;
ALTER TABLE products ADD COLUMN is_active BOOLEAN DEFAULT TRUE;
-- Drop old UNIQUE (asin), add new:
ALTER TABLE products ADD CONSTRAINT uq_platform_product UNIQUE (platform, platform_id);

-- CrawlTask: add platform for worker filtering
ALTER TABLE crawl_tasks ADD COLUMN platform VARCHAR(30) DEFAULT 'amazon';

-- DealDismissal: rename dismissed_asin → dismissed_platform_id, widen to VARCHAR(30)
ALTER TABLE deal_dismissals RENAME COLUMN dismissed_asin TO dismissed_platform_id;
ALTER TABLE deal_dismissals ALTER COLUMN dismissed_platform_id TYPE VARCHAR(30);
```

**Platform ID formats**:
| Platform | ID field | Length | Example |
|----------|----------|--------|---------|
| Amazon | ASIN | 10 chars | B08N5WRWNW |
| Best Buy | SKU | 7 digits | 6525401 |
| Walmart | Item ID | 9-12 digits | 123456789012 |

**price_type vocabulary per platform**:
| Platform | price_type values | Notes |
|----------|-------------------|-------|
| Amazon | `amazon`, `new`, `used` | From CCC chart curves |
| Best Buy | `regular`, `sale` | From API response |
| Walmart | `regular`, `rollback` | TBD when implemented |

**source field values**:
| Platform | source value |
|----------|-------------|
| Amazon (pixel) | `ccc_chart` |
| Amazon (OCR) | `ccc_legend` |
| Best Buy | `bestbuy_api` |
| Walmart | `walmart_scrape` |

**URL semantics**: Canonical product URL (without affiliate tag). Affiliate tag appended at display time by the bot. Nullable — Amazon URLs are constructible from ASIN, but stored for consistency.

**is_active update mechanism**: During crawl, if fetch returns 404/gone → `is_active = False`. Monthly re-check job for inactive products (attempt re-fetch, re-activate if available).

**Cross-platform product matching** deferred to future phase. Will use UPC/EAN codes when needed.

### 3.2 ExtractionRun → FetchRun (Generalized)

**Decision**: Rename `ExtractionRun` to `FetchRun` and make CCC-specific fields nullable.

```sql
ALTER TABLE extraction_runs RENAME TO fetch_runs;
ALTER TABLE fetch_runs ALTER COLUMN chart_path DROP NOT NULL;  -- nullable for API-based platforms
-- ocr_confidence: already nullable
-- validation_passed: already nullable
ALTER TABLE fetch_runs ADD COLUMN platform VARCHAR(30) DEFAULT 'amazon';

-- Update FK references in ORM code (DB handles OID-based FK automatically):
-- PriceHistory.extraction_id FK string: "extraction_runs.id" → "fetch_runs.id"
-- PriceSummary.extraction_id FK string: "extraction_runs.id" → "fetch_runs.id"
```

Best Buy API responses: `chart_path = NULL`, `ocr_confidence = NULL`, `validation_passed = NULL`, `status = 'success'` (API data is authoritative, no cross-validation needed).

### 3.3 Platform Crawler Plugin System

**Decision**: Split Fetcher + Parser (separation of concerns).

```python
# Type definitions
RawData = bytes | dict[str, Any]
# bytes: PNG image data (CCC), HTML (Walmart)
# dict: JSON response (Best Buy API)

@dataclass(frozen=True)
class PriceRecord:
    price_type: str       # "amazon", "new", "used", "regular", "sale"
    recorded_date: date
    price_cents: int
    source: str           # "ccc_chart", "bestbuy_api", etc.

class PlatformFetcher(Protocol):
    """Responsible for obtaining raw data from a platform."""
    async def fetch(self, platform_id: str) -> RawData

class PlatformParser(Protocol):
    """Responsible for extracting price data from raw data."""
    def parse(self, raw_data: RawData) -> list[PriceRecord]
```

Shared infrastructure (rate limiting, retries, proxy rotation) lives in the orchestrator layer, not in individual plugins.

Platform implementations:
- **AmazonFetcher/Parser**: CCC chart PNG download + pixel analysis + OCR (existing code, refactored)
- **BestBuyFetcher/Parser**: Official REST API (free, register for API key)
- **WalmartFetcher/Parser**: Web scraping with proxy pool (future)

### 3.4 Task Scheduling

**Decision**: DB polling with TaskQueue Protocol abstraction.

```python
class TaskQueue(Protocol):
    async def pop_next(self, platform: str) -> Task | None
    async def complete(self, task_id: int) -> None
    async def fail(self, task_id: int, error: str) -> None

class DbTaskQueue:
    async def pop_next(self, platform: str) -> Task | None:
        """SELECT ... FOR UPDATE SKIP LOCKED to prevent duplicate processing."""
        # SELECT FROM crawl_tasks
        # WHERE status = 'pending' AND platform = :platform
        # ORDER BY priority, scheduled_at
        # LIMIT 1
        # FOR UPDATE SKIP LOCKED
```

**Concurrency safety**: `SELECT FOR UPDATE SKIP LOCKED` ensures multiple workers never grab the same task. `SKIP LOCKED` is non-blocking — if a row is locked by another worker, it's simply skipped.

**Recovery state machine**: Remains per-worker (each worker tracks its own failure count and state). This is correct because recovery is about "is this worker's network/proxy healthy", not a global state. If a worker's proxy gets blocked, only that worker pauses — others continue.

**Platform filtering**: Workers pass their `platform` parameter to `pop_next()`, only receiving tasks for their platform. `CrawlTask.platform` column enables this filter.

Migration to Redis is a 1-class change (~50 lines) when needed. No application code changes.

### 3.5 ASIN Discovery System

**Decision**: Multi-channel discovery with validation-before-scale pipeline.

Discovery channels:
| Channel | Est. yield | Method |
|---------|-----------|--------|
| CCC top_drops/popular | ~10K | Existing harvester |
| Best Buy API catalog | ~1M | Official API enumeration |
| Amazon category sitemap | ~millions | Public XML sitemap |
| Reddit deal communities | ~tens of K | JSON API (spike exists) |

Validation pipeline (Amazon-specific — Best Buy products are validated by API existence):
```
discover(ASIN) → status=discovered
       ↓
fetch CCC chart → has data?
       ↓              ↓
    status=active    status=no_data (skip)
       ↓
 enter crawl queue
```

Small batch validation (100) → check hit rate → adjust channel strategy → scale up.

### 3.6 Worker Deployment

**Decision**: Docker Compose, one compose file per VPS.

```yaml
# docker-compose.yml (each VPS)
services:
  worker-amazon:
    image: cps-worker
    command: ["python", "-m", "cps.worker", "--platform", "amazon"]
    environment:
      - PROXY_URL=socks5://proxy-a:1080
      - DATABASE_URL=postgresql+asyncpg://...
    deploy:
      replicas: 3  # scale with --scale

  worker-bestbuy:
    image: cps-worker
    command: ["python", "-m", "cps.worker", "--platform", "bestbuy"]
    environment:
      - BESTBUY_API_KEY=${BESTBUY_API_KEY}
      - DATABASE_URL=postgresql+asyncpg://...
      # No proxy needed - official API

  postgres:
    image: postgres:16-alpine
    # Only on primary VPS; workers on other VPS connect remotely
```

**Worker entry point** (`cps/worker.py`):
```python
async def run_worker(platform: str):
    queue = DbTaskQueue(session)
    fetcher = get_fetcher(platform)  # registry lookup
    parser = get_parser(platform)
    while True:
        task = await queue.pop_next(platform)
        if task is None:
            await asyncio.sleep(5)  # no work, wait
            continue
        raw = await fetcher.fetch(task.platform_id)
        records = parser.parse(raw)
        await store_records(task.product_id, records)
        await queue.complete(task.id)
```

Upgrade path: Docker Compose → Docker Swarm (config change only, zero code changes).

### 3.7 Tiered Crawl Scheduling

Not all products need the same refresh frequency:

| Tier | % of products | Crawl interval | Example |
|------|--------------|----------------|---------|
| Hot | 10% | 7 days | Popular, high price volatility |
| Warm | 30% | 30 days | Average products |
| Cold | 60% | 90 days | Stable price, low demand |

At 100M products: ~3.1M crawls/day → 36 workers → 4 VPS.

**Implementation timing**: Phase 1-3 use current hardcoded 7-day interval. Tiered scheduling is Phase 4 when product count exceeds ~1M and not all products need weekly refresh.

## 4. Scaling Projections

| Scale | Workers | VPS | VPS cost | Proxy cost | Total/month | DB concern |
|-------|---------|-----|----------|-----------|-------------|------------|
| 50K | 1 | 1 × $10 | $10 | $0 | **~$10** | None |
| 500K | 6 | 1 × $10 | $10 | $0 | **~$15** | None |
| 5M | 8 | 2 × $10 | $20 | $30 | **~$60** | None |
| 50M | 20 | 3 × $10 | $30 | $60 | **~$150** | Monitor price_history size |
| 100M | 36 | 4 × $10 | $40 | $100 | **~$300** | TimescaleDB or cold/hot split |

Note: Proxy costs are for datacenter proxies (~$3/IP/month). Residential proxies would be higher.

### Future upgrades (when needed, not now):
- **DB polling → Redis**: When 10+ cross-machine workers (half day)
- **PostgreSQL → TimescaleDB**: When price_history > 1B rows (~2 SQL commands, 1 hour)
- **Docker Compose → Swarm**: When 5+ VPS (config change, 2 hours)
- **Cold/hot data split**: When storage > 5TB (archive script, 1 day)

## 5. Phased Execution Plan

### Phase 1A — Multi-Platform Migration (2-3 days)
> Pure rename/migration — no new features, reduce risk by isolating breaking changes.
- [ ] Alembic migration `003_multi_platform.py`:
  - Add `platform` column to products (default 'amazon')
  - Rename `asin` → `platform_id`, widen to VARCHAR(30)
  - Add `url`, `is_active` to products
  - Add `platform` to crawl_tasks
  - Rename `extraction_runs` → `fetch_runs`, add `platform`
  - Rename `dismissed_asin` → `dismissed_platform_id` in deal_dismissals
  - Update unique constraints and indexes
- [ ] Code migration (file-by-file, see Section 6):
  - Models, services, CLI, bot handlers, seeds, jobs, tests
  - `asin_parser.py` → `product_id_parser.py` (multi-platform URL parsing)
  - `affiliate.py` → platform-aware link builder
- [ ] All existing tests passing with new schema
- [ ] Gate: `uv run pytest` green before proceeding to 1B

### Phase 1B — New Architecture (2-3 days)
> Build new abstractions on top of the migrated codebase.
- [ ] Implement TaskQueue Protocol + DbTaskQueue (SELECT FOR UPDATE SKIP LOCKED)
- [ ] Refactor pipeline into Fetcher/Parser split
- [ ] Build ASIN discovery validation pipeline
- [ ] Gate: all new + existing tests passing

### Phase 2 — Scale Amazon + Add Best Buy (2-3 days)
- [ ] Multi-channel ASIN collection → validate → target 500K active Amazon ASINs
- [ ] Implement BestBuyFetcher + BestBuyParser
- [ ] Register Best Buy API key
- [ ] Target: 1M+ total product coverage (500K Amazon + 1M Best Buy)
- [ ] Start price crawling in background

### Phase 3 — Telegram Bot Adaptation (2-3 days)
- [ ] Bot handlers: replace all `Product.asin` with `Product.platform_id`
- [ ] `asin_parser.py` → support Best Buy URLs, Walmart URLs
- [ ] `build_product_link()` → platform-aware affiliate links
- [ ] Price report display → platform-aware (show "Buy on Amazon" / "Buy on Best Buy")
- [ ] Search waterfall → multi-platform search
- [ ] Config: `demo_asin` → `demo_product` with platform
- [ ] Cross-platform price comparison display

### Phase 4 — Scale & Walmart (as needed)
- [ ] Add VPS / proxy pool
- [ ] WalmartFetcher + WalmartParser
- [ ] Tiered crawl scheduling (hot/warm/cold intervals)
- [ ] Database optimization if needed (TimescaleDB / cold-hot split)

## 6. Code Migration Checklist

Files requiring `asin` → `platform_id` changes:

### Models & DB
- [ ] `src/cps/db/models.py` — Product.asin, DealDismissal.dismissed_asin, ExtractionRun → FetchRun, FK strings in PriceHistory/PriceSummary
- [ ] `alembic/versions/003_multi_platform.py` — new migration (test against DB copy first)

### Services
- [ ] `src/cps/services/asin_parser.py` → rename to `product_id_parser.py`, support multi-platform URLs
- [ ] `src/cps/services/affiliate.py` — `build_product_link()` platform-aware
- [ ] `src/cps/services/deal_service.py` — dismissed_asin references
- [ ] `src/cps/services/crawl_service.py` — upsert_crawl_task()
- [ ] `src/cps/services/monitor_service.py` — Product.asin queries

### Jobs
- [ ] `src/cps/jobs/deal_scanner.py` — dismissed_asin, deal.asin, build_product_link(deal.asin)
- [ ] `src/cps/jobs/price_checker.py` — product.asin, build_product_link(product.asin)
- [ ] `src/cps/jobs/crawl_failure_notifier.py` — product.asin in template call

### Pipeline
- [ ] `src/cps/pipeline/orchestrator.py` — asin references, ExtractionRun → FetchRun, add platform filtering
- [ ] `src/cps/crawler/downloader.py` — `download(asin: str)` parameter
- [ ] `src/cps/crawler/storage.py` — directory structure uses asin

### Seeds
- [ ] `src/cps/seeds/manager.py` — ASIN-specific validation (needs platform-aware validation)

### CLI
- [ ] `src/cps/cli.py` — seed/crawl commands, status display, ExtractionRun → FetchRun references

### Bot
- [ ] `src/cps/bot/handlers/price_check.py` — Product.asin queries
- [ ] `src/cps/bot/handlers/callbacks.py` — asin references
- [ ] `src/cps/bot/handlers/start.py` — demo_asin
- [ ] `src/cps/bot/handlers/monitors.py` — Product.asin queries
- [ ] `src/cps/bot/handlers/settings.py` — asin references (verify)
- [ ] `src/cps/bot/messages.py` — `crawl_failed(self, asin: str)` method signature
- [ ] `src/cps/bot/keyboards.py` — 5 functions take `asin` parameter, `dismiss_asin:` callback data

### Tests
- [ ] `tests/unit/test_asin_parser.py` → rename, add multi-platform cases
- [ ] `tests/unit/test_deal_service.py` — dismissed_asin
- [ ] `tests/unit/test_db_models.py` — Product.asin
- [ ] `tests/unit/test_handlers.py` — asin references
- [ ] `tests/unit/test_keyboards.py` — asin parameter
- [ ] `tests/unit/test_search_service.py` — asin references
- [ ] `tests/unit/test_storage.py` — asin in path
- [ ] `tests/unit/test_orchestrator_upsert.py` — asin references
- [ ] `tests/integration/test_pipeline.py` — asin references
- [ ] `tests/integration/test_downloader.py` — asin parameter
- [ ] `tests/integration/test_auto_recovery.py` — asin references
- [ ] `tests/integration/test_crash_recovery.py` — asin references
- [ ] `tests/integration/test_monitor_repo.py` — asin references

## 7. Non-Goals (Explicit)

- **Cross-platform product matching**: Not in scope. Each platform's products are independent entries.
- **Kubernetes**: Not needed. Docker Compose → Swarm covers the scaling path.
- **Real-time price updates**: Batch crawling on intervals is sufficient.
- **eBay support**: Auction model differs fundamentally; evaluate separately if needed.
- **Celery / heavy task frameworks**: TaskQueue Protocol is lighter and sufficient.
