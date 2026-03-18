# Phase 1A: Multi-Platform Migration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename all `asin` → `platform_id`, `ExtractionRun` → `FetchRun`, `dismissed_asin` → `dismissed_platform_id` across DB, ORM, services, handlers, tests. Add `platform` column. No new features — pure rename/migration to enable multi-platform support.

**Architecture:** Bottom-up migration: DB schema first (Alembic), then ORM models, then services/pipeline/bot/tests. All changes default to `platform='amazon'` — existing behavior preserved. 247 tests must stay green.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, Alembic, PostgreSQL 16, pytest, Typer CLI, python-telegram-bot

**Deployment:** All 13 tasks MUST be deployed atomically — the migration and all code changes ship together. Individual git commits are for development tracking only, not for incremental deployment.

**Review fixes applied:** 4 CRITICAL + 11 IMPORTANT issues from architecture + security review.

---

### Task 1: Alembic Migration 003

**Files:**
- Create: `alembic/versions/003_multi_platform.py`

**Step 1: Write the migration**

```python
"""Multi-platform support — rename asin/extraction_runs, add platform columns.

Revision ID: 003
Revises: 002
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"


def upgrade() -> None:
    # --- products ---
    # Drop old unique constraint on asin
    op.drop_constraint("products_asin_key", "products", type_="unique")

    # Rename asin → platform_id and widen
    op.alter_column("products", "asin", new_column_name="platform_id")
    op.alter_column(
        "products", "platform_id",
        type_=sa.String(30), existing_type=sa.String(10),
        existing_nullable=False,
    )

    # Add new columns
    op.add_column("products", sa.Column(
        "platform", sa.String(30), nullable=False, server_default="amazon",
    ))
    op.add_column("products", sa.Column("url", sa.Text, nullable=True))
    op.add_column("products", sa.Column(
        "is_active", sa.Boolean, nullable=False, server_default="true",
    ))

    # New compound unique constraint
    op.create_unique_constraint(
        "uq_platform_product", "products", ["platform", "platform_id"],
    )

    # CHECK: platform must be a known value (extend when adding new platforms)
    op.create_check_constraint(
        "ck_products_platform_valid", "products",
        "platform IN ('amazon')",
    )

    # CHECK: url must use HTTPS if present (prevent SSRF vectors)
    op.create_check_constraint(
        "ck_products_url_scheme", "products",
        "url IS NULL OR url ~ '^https://'",
    )

    # Index for platform + active filtering
    op.create_index("idx_products_platform_active", "products", ["platform", "is_active"])

    # --- extraction_runs → fetch_runs ---
    op.rename_table("extraction_runs", "fetch_runs")

    # Make chart_path nullable (API-based platforms have no chart)
    op.alter_column(
        "fetch_runs", "chart_path",
        existing_type=sa.String(500), nullable=True,
    )

    # Add platform column
    op.add_column("fetch_runs", sa.Column(
        "platform", sa.String(30), nullable=False, server_default="amazon",
    ))
    op.create_check_constraint(
        "ck_fetch_runs_platform_valid", "fetch_runs",
        "platform IN ('amazon')",
    )

    # Rename indexes for clarity (PG DDL is transactional — safe within migration)
    op.execute(sa.text("ALTER INDEX idx_er_product RENAME TO idx_fr_product"))
    op.execute(sa.text("ALTER INDEX idx_er_status RENAME TO idx_fr_status"))

    # --- crawl_tasks ---
    op.add_column("crawl_tasks", sa.Column(
        "platform", sa.String(30), nullable=False, server_default="amazon",
    ))
    op.create_check_constraint(
        "ck_crawl_tasks_platform_valid", "crawl_tasks",
        "platform IN ('amazon')",
    )

    # --- deal_dismissals ---
    op.drop_constraint("ck_dismissals_has_target", "deal_dismissals", type_="check")
    op.alter_column(
        "deal_dismissals", "dismissed_asin",
        new_column_name="dismissed_platform_id",
    )
    op.alter_column(
        "deal_dismissals", "dismissed_platform_id",
        type_=sa.String(30), existing_type=sa.String(10),
        existing_nullable=True,
    )
    op.create_check_constraint(
        "ck_dismissals_has_target", "deal_dismissals",
        "dismissed_category IS NOT NULL OR dismissed_platform_id IS NOT NULL",
    )


def downgrade() -> None:
    # Safety: block downgrade if data would be truncated or lost
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM products WHERE LENGTH(platform_id) > 10) THEN
                RAISE EXCEPTION 'Downgrade blocked: platform_id values exceed VARCHAR(10). Remove or shorten them first.';
            END IF;
            IF EXISTS (SELECT 1 FROM deal_dismissals WHERE LENGTH(dismissed_platform_id) > 10) THEN
                RAISE EXCEPTION 'Downgrade blocked: dismissed_platform_id values exceed VARCHAR(10). Remove or shorten them first.';
            END IF;
            IF EXISTS (SELECT 1 FROM fetch_runs WHERE chart_path IS NULL) THEN
                RAISE EXCEPTION 'Downgrade blocked: fetch_runs has NULL chart_path rows. Delete them first.';
            END IF;
        END $$;
    """))

    # --- deal_dismissals ---
    op.drop_constraint("ck_dismissals_has_target", "deal_dismissals", type_="check")
    op.alter_column(
        "deal_dismissals", "dismissed_platform_id",
        new_column_name="dismissed_asin",
    )
    op.alter_column(
        "deal_dismissals", "dismissed_asin",
        type_=sa.String(10), existing_type=sa.String(30),
        existing_nullable=True,
    )
    op.create_check_constraint(
        "ck_dismissals_has_target", "deal_dismissals",
        "dismissed_category IS NOT NULL OR dismissed_asin IS NOT NULL",
    )

    # --- crawl_tasks ---
    op.drop_constraint("ck_crawl_tasks_platform_valid", "crawl_tasks", type_="check")
    op.drop_column("crawl_tasks", "platform")

    # --- fetch_runs → extraction_runs ---
    op.execute(sa.text("ALTER INDEX idx_fr_product RENAME TO idx_er_product"))
    op.execute(sa.text("ALTER INDEX idx_fr_status RENAME TO idx_er_status"))
    op.drop_constraint("ck_fetch_runs_platform_valid", "fetch_runs", type_="check")
    op.drop_column("fetch_runs", "platform")
    op.alter_column(
        "fetch_runs", "chart_path",
        existing_type=sa.String(500), nullable=False,
    )
    op.rename_table("fetch_runs", "extraction_runs")

    # --- products ---
    op.drop_constraint("uq_platform_product", "products", type_="unique")
    op.drop_index("idx_products_platform_active", "products")
    op.drop_constraint("ck_products_url_scheme", "products", type_="check")
    op.drop_constraint("ck_products_platform_valid", "products", type_="check")
    op.drop_column("products", "is_active")
    op.drop_column("products", "url")
    op.drop_column("products", "platform")
    op.alter_column(
        "products", "platform_id",
        type_=sa.String(10), existing_type=sa.String(30),
        existing_nullable=False,
    )
    op.alter_column("products", "platform_id", new_column_name="asin")
    op.create_unique_constraint("products_asin_key", "products", ["asin"])
```

**Step 2: Verify migration syntax**

Run: `uv run python -c "import alembic.versions" 2>&1 || echo "syntax check via import"`

Verify: no syntax errors in the file.

**Step 3: Commit**

```bash
git add alembic/versions/003_multi_platform.py
git commit -m "feat: add Alembic migration 003 for multi-platform schema"
```

---

### Task 2: ORM Models

**Files:**
- Modify: `src/cps/db/models.py`

**Step 1: Update Product model**

In `Product` class (line 34-61):
- `asin: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)` → `platform_id: Mapped[str] = mapped_column(String(30), nullable=False)`
- Add after `platform_id`: `platform: Mapped[str] = mapped_column(String(30), nullable=False, server_default="amazon")`
- Add: `url: Mapped[str | None] = mapped_column(Text, nullable=True)`
- Add: `is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")`
- Relationship `extraction_runs` → `fetch_runs`: `extraction_runs: Mapped[list["ExtractionRun"]]` → `fetch_runs: Mapped[list["FetchRun"]]`
- Update `back_populates="product"` stays the same
- `__table_args__`: change to `(Index("idx_products_category", "category"), UniqueConstraint("platform", "platform_id", name="uq_platform_product"),)`

**Step 2: Rename ExtractionRun → FetchRun**

Rename class `ExtractionRun` → `FetchRun` (line 64-87):
- `__tablename__ = "extraction_runs"` → `"fetch_runs"`
- `chart_path: Mapped[str] = mapped_column(String(500), nullable=False)` → `chart_path: Mapped[str | None] = mapped_column(String(500), nullable=True)`
- Add: `platform: Mapped[str] = mapped_column(String(30), nullable=False, server_default="amazon")`
- Relationship: `back_populates="extraction_runs"` → `back_populates="fetch_runs"`
- Index names: `"idx_er_product"` → `"idx_fr_product"`, `"idx_er_status"` → `"idx_fr_status"`

**Step 3: Update FK references**

- `PriceHistory.extraction_id` (line 109-110): FK `"extraction_runs.id"` → `"fetch_runs.id"`
- `PriceSummary.extraction_id` (line 140-141): FK `"extraction_runs.id"` → `"fetch_runs.id"`

**Step 4: Update CrawlTask**

Add to `CrawlTask` class after `product_id` (around line 196):
```python
platform: Mapped[str] = mapped_column(
    String(30), nullable=False, server_default="amazon"
)
```

**Step 5: Update DealDismissal**

- `dismissed_asin: Mapped[str | None] = mapped_column(String(10), nullable=True)` → `dismissed_platform_id: Mapped[str | None] = mapped_column(String(30), nullable=True)`
- CheckConstraint: `"dismissed_category IS NOT NULL OR dismissed_asin IS NOT NULL"` → `"dismissed_category IS NOT NULL OR dismissed_platform_id IS NOT NULL"`

**Step 6: Commit**

```bash
git add src/cps/db/models.py
git commit -m "refactor: rename asin→platform_id, ExtractionRun→FetchRun in ORM models"
```

---

### Task 3: Test Fixtures & Model Unit Tests

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/unit/test_user_models.py`

**Step 1: Update conftest.py**

- `sample_asin` fixture → `sample_platform_id` (rename fixture, return same value)
- `sample_asins` fixture → `sample_platform_ids` (rename fixture, return same value)

```python
@pytest.fixture
def sample_platform_id() -> str:
    """Return a sample platform ID for testing."""
    return "B08N5WRWNW"


@pytest.fixture
def sample_platform_ids() -> list[str]:
    """Return a list of sample platform IDs for batch testing."""
    return [
        "B08N5WRWNW",
        "B09V3KXJPB",
        "B0BSHF7WHW",
        "B0D1XD1ZV3",
        "B0CHX3QBCH",
    ]
```

**Step 2: Update test_user_models.py**

In `TestDealDismissal.test_columns_exist` (line 80-83):
- Change `"dismissed_asin"` → `"dismissed_platform_id"` in the expected columns set

**Step 3: Run unit model tests**

Run: `uv run pytest tests/unit/test_user_models.py -v`
Expected: All pass

**Step 4: Commit**

```bash
git add tests/conftest.py tests/unit/test_user_models.py
git commit -m "refactor: update test fixtures for platform_id rename"
```

---

### Task 4: Services — Parser, Affiliate, Deal, Crawl

**Files:**
- Rename: `src/cps/services/asin_parser.py` → `src/cps/services/product_id_parser.py`
- Modify: `src/cps/services/affiliate.py`
- Modify: `src/cps/services/deal_service.py`
- Modify: `src/cps/services/crawl_service.py` (verify — likely no `asin` refs)
- Rename: `tests/unit/test_asin_parser.py` → `tests/unit/test_product_id_parser.py`
- Modify: `tests/unit/test_deal_service.py`

**Step 1: Rename asin_parser.py → product_id_parser.py**

```bash
git mv src/cps/services/asin_parser.py src/cps/services/product_id_parser.py
```

Update the file content:
- Module docstring: change "Amazon URL, ASIN, or natural language" → "product URL, product ID, or natural language"
- `InputType.ASIN = "asin"` → `InputType.PRODUCT_ID = "product_id"`
- `ParseResult.asin: str | None` → `ParseResult.platform_id: str | None`
- Add `ParseResult.platform: str = "amazon"` (default platform)
- `_ASIN_PATTERN` → `_ASIN_PATTERN` (keep name — it's still matching ASIN format)
- In `parse_input()`: return `ParseResult(InputType.URL, platform_id=..., platform="amazon")` and `ParseResult(InputType.PRODUCT_ID, platform_id=...)`

Full updated file:
```python
"""Classify user input as product URL, product ID, or natural language query.

Detection order (per spec Section 2.2):
1. URL regex — contains amazon.com/dp/ or amazon.com/gp/product/
2. Product ID regex — standalone B[A-Z0-9]{9} (Amazon ASIN)
3. Everything else — natural language
"""
import re
from dataclasses import dataclass, field
from enum import Enum


class InputType(Enum):
    URL = "url"
    PRODUCT_ID = "product_id"
    NATURAL_LANGUAGE = "natural_language"


@dataclass(frozen=True)
class ParseResult:
    input_type: InputType
    platform_id: str | None = None
    platform: str = "amazon"
    query: str | None = None


_URL_PATTERN = re.compile(
    r"amazon\.com/(?:[\w-]+/)?(?:dp|gp/product)/([A-Z0-9]{10})", re.IGNORECASE
)
_ASIN_PATTERN = re.compile(r"\bB[A-Z0-9]{9}\b")


def parse_input(text: str) -> ParseResult:
    """Classify and extract product identifier from user message."""
    # 1. URL regex
    url_match = _URL_PATTERN.search(text)
    if url_match:
        return ParseResult(
            InputType.URL,
            platform_id=url_match.group(1).upper(),
            platform="amazon",
        )

    # 2. Product ID regex (Amazon ASIN)
    asin_match = _ASIN_PATTERN.search(text)
    if asin_match:
        return ParseResult(
            InputType.PRODUCT_ID,
            platform_id=asin_match.group(0),
            platform="amazon",
        )

    # 3. Natural language
    return ParseResult(InputType.NATURAL_LANGUAGE, query=text.strip())
```

**Step 2: Rename and update test_asin_parser.py**

```bash
git mv tests/unit/test_asin_parser.py tests/unit/test_product_id_parser.py
```

Update imports and assertions:
- `from cps.services.asin_parser import ...` → `from cps.services.product_id_parser import ...`
- `InputType.ASIN` → `InputType.PRODUCT_ID`
- `ParseResult(InputType.URL, asin="B08N5WRWNW")` → `ParseResult(InputType.URL, platform_id="B08N5WRWNW", platform="amazon")`
- `ParseResult(InputType.ASIN, asin=...)` → `ParseResult(InputType.PRODUCT_ID, platform_id=...)`
- `ParseResult(InputType.NATURAL_LANGUAGE, query=...)` stays the same
- Class name `TestAsinParsing` → `TestProductIdParsing`

**Step 3: Update affiliate.py**

```python
"""Affiliate link builder — every user-facing URL carries the tag."""
from urllib.parse import quote_plus


def build_product_link(platform_id: str, tag: str, platform: str = "amazon") -> str:
    """Build tagged product URL for the given platform.

    Raises:
        ValueError: If platform is not recognized.
    """
    if platform == "amazon":
        return f"https://www.amazon.com/dp/{platform_id}?tag={tag}"
    raise ValueError(f"Unknown platform: '{platform}'. Cannot build product link.")


def build_search_link(query: str, tag: str) -> str:
    """Build tagged search URL for fallback tier."""
    return f"https://www.amazon.com/s?k={quote_plus(query)}&tag={tag}"
```

**Step 4: Update deal_service.py**

- `Deal` dataclass: `asin: str` → `platform_id: str`, add `platform: str = "amazon"`
- All `product.asin` → `product.platform_id`
- `dismissed_asins` parameter → `dismissed_platform_ids`
- `d.asin` → `d.platform_id` in filter logic

Key changes:
```python
@dataclass(frozen=True)
class Deal:
    platform_id: str
    platform: str
    title: str
    category: str | None
    current: int     # cents
    was: int         # highest price, cents
```

In `find_related()`, `find_global_best()`, `find_by_search_pattern()`:
- `Deal(asin=product.asin, ...)` → `Deal(platform_id=product.platform_id, platform=product.platform, ...)`
- `product.title or product.asin` → `product.title or product.platform_id`

In `filter_dismissed()`:
- `dismissed_asins: set[str] | None` → `dismissed_platform_ids: set[str] | None`
- `d.asin in dismissed_asins` → `d.platform_id in dismissed_platform_ids`

**Step 5: Update test_deal_service.py**

- `MagicMock(asin=..., ...)` → `MagicMock(platform_id=..., platform="amazon", ...)`
- `deals[0].asin` → `deals[0].platform_id`
- `Deal(asin="B1", ...)` → `Deal(platform_id="B1", platform="amazon", ...)`

**Step 6: Run tests**

Run: `uv run pytest tests/unit/test_product_id_parser.py tests/unit/test_deal_service.py -v`
Expected: All pass

**Step 7: Commit**

```bash
git add -A src/cps/services/ tests/unit/test_product_id_parser.py tests/unit/test_deal_service.py
git commit -m "refactor: rename asin→platform_id in services layer"
```

---

### Task 5: Crawler — Storage & Downloader

**Files:**
- Modify: `src/cps/crawler/storage.py`
- Modify: `src/cps/crawler/downloader.py`
- Modify: `tests/unit/test_storage.py`
- Modify: `tests/integration/test_downloader.py`

**Step 1: Update storage.py**

- `def save(self, asin: str, png_bytes: bytes)` → `def save(self, platform_id: str, png_bytes: bytes)`
- Internal: all `asin` → `platform_id`
- Docstring: "ASIN" → "platform product ID"
- Rename `_ASIN_PATTERN` → `_AMAZON_ASIN_PATTERN` to clarify it's Amazon-specific
- Validation stays same (10-char alphanumeric — it's still Amazon-specific for CCC)
- Error message: `"Invalid ASIN: ..."` → `"Invalid platform_id: '{platform_id}' — must be exactly 10 alphanumeric characters (Amazon ASIN format)"`

```python
# At class level, rename the pattern for clarity
_AMAZON_ASIN_PATTERN = re.compile(r"^[A-Za-z0-9]{10}$")

def save(self, platform_id: str, png_bytes: bytes) -> Path:
    """Save a PNG chart image for the given product.

    Args:
        platform_id: Product identifier (10 alphanumeric chars for Amazon ASIN).
        png_bytes: Raw PNG image data.

    Returns:
        Absolute path to the saved file.

    Raises:
        ValueError: If platform_id is not exactly 10 alphanumeric characters.
    """
    # Amazon ASIN format validation — CCC storage is Amazon-specific
    if not self._AMAZON_ASIN_PATTERN.match(platform_id):
        raise ValueError(
            f"Invalid platform_id: '{platform_id}' — must be exactly 10 alphanumeric characters"
        )

    prefix = platform_id[:2]
    today = date.today().isoformat()

    target_dir = self._data_dir / "charts" / prefix / platform_id
    target_dir.mkdir(parents=True, exist_ok=True)

    file_path = target_dir / f"{today}.png"
    file_path.write_bytes(png_bytes)

    return file_path.resolve()
```

**Step 2: Update downloader.py**

- `async def download(self, asin: str) -> bytes:` → `async def download(self, platform_id: str) -> bytes:`
- Docstring: "ASIN" → "platform product ID"
- URL construction: `f"{self._base_url}/{asin}/..."` → `f"{self._base_url}/{platform_id}/..."`
- Error messages: `f"... for ASIN {asin}"` → `f"... for {platform_id}"`

**Step 3: Update test_storage.py**

- All `asin="B..."` → `platform_id="B..."`
- All `storage.save(asin=...)` → `storage.save(platform_id=...)`
- Error match: `match="[Ii]nvalid.*ASIN"` → `match="[Ii]nvalid.*platform_id"`
- Docstrings: "ASIN" → "platform_id"

**Step 4: Update test_downloader.py**

- `SAMPLE_ASIN = "B08N5WRWNW"` → `SAMPLE_PLATFORM_ID = "B08N5WRWNW"`
- All `downloader.download(SAMPLE_ASIN)` → `downloader.download(SAMPLE_PLATFORM_ID)`
- Assertion: `assert SAMPLE_ASIN in url` → `assert SAMPLE_PLATFORM_ID in url`

**Step 5: Run tests**

Run: `uv run pytest tests/unit/test_storage.py tests/integration/test_downloader.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/cps/crawler/storage.py src/cps/crawler/downloader.py tests/unit/test_storage.py tests/integration/test_downloader.py
git commit -m "refactor: rename asin→platform_id in crawler layer"
```

---

### Task 6: Pipeline — Orchestrator

**Files:**
- Modify: `src/cps/pipeline/orchestrator.py`
- Modify: `tests/unit/test_orchestrator_upsert.py`

**Step 1: Update orchestrator.py imports and references**

- Import: `ExtractionRun` → `FetchRun` (line 23)
- `_build_price_summary_upsert()`: param `extraction_id` stays — it's the DB column name in `price_history` and `price_summary`. Not renamed because `price_history` is a partitioned table (renaming column across parent + 7 yearly partitions is complex). Add a TODO comment in the function:
  `# TODO: extraction_id column kept for compatibility with partitioned price_history table. Consider renaming to fetch_run_id in a future migration.`
- `_process_one()` (line 181+):
  - `asin = product.asin` → `platform_id = product.platform_id` (line 188)
  - `self._downloader.download(asin)` → `self._downloader.download(platform_id)` (line 197)
  - `self._storage.save(asin, png_bytes)` → `self._storage.save(platform_id, png_bytes)` (line 200)
  - `run = ExtractionRun(...)` → `run = FetchRun(...)` (line 235)
  - All `log.xxx(..., asin=asin)` → `log.xxx(..., platform_id=platform_id)` (lines 286, 293, 300, 311, 318)

**Step 2: Update test_orchestrator_upsert.py**

- No changes needed — `extraction_id` param name is a DB column, not being renamed.
- Verify the import still works: `from cps.pipeline.orchestrator import _build_price_summary_upsert`

**Step 3: Run test**

Run: `uv run pytest tests/unit/test_orchestrator_upsert.py -v`
Expected: All pass

**Step 4: Commit**

```bash
git add src/cps/pipeline/orchestrator.py tests/unit/test_orchestrator_upsert.py
git commit -m "refactor: rename asin→platform_id, ExtractionRun→FetchRun in orchestrator"
```

---

### Task 7: Seeds — Manager

**Files:**
- Modify: `src/cps/seeds/manager.py`
- Modify: `tests/unit/test_seed_manager.py`

**Step 1: Update manager.py**

- `ASIN_PATTERN` stays (still validates Amazon ASIN format)
- `_validate_asin(asin)` → `_validate_platform_id(platform_id)` — same regex, renamed param
- Error message: `"Invalid ASIN format: ..."` → `"Invalid platform_id format: '{platform_id}'. Must be 10-11 alphanumeric characters."`
- Variable names: `asins` → `platform_ids`, `unique_asins` → `unique_ids`, `existing` stays
- `select(Product.asin).where(Product.asin.in_(...))` → `select(Product.platform_id).where(Product.platform_id.in_(...))`
- `Product(asin=asin)` → `Product(platform_id=platform_id)`
- `add_single(self, asin: str)` → `add_single(self, platform_id: str)`
- `select(Product).where(Product.asin == asin)` → `select(Product).where(Product.platform_id == platform_id)`

**Step 2: Update test_seed_manager.py**

- Docstrings: "ASIN" → "platform_id" where describing the concept
- `manager.add_single("B00TEST0001")` stays same (value unchanged, just param name changed)
- Class `TestASINValidation` → `TestPlatformIdValidation`
- Test method names: `test_too_short_asin_...` → `test_too_short_platform_id_...` (optional, not required)

**Step 3: Run tests**

Run: `uv run pytest tests/unit/test_seed_manager.py -v`
Expected: All pass

**Step 4: Commit**

```bash
git add src/cps/seeds/manager.py tests/unit/test_seed_manager.py
git commit -m "refactor: rename asin→platform_id in seed manager"
```

---

### Task 8: Config + Bot Messaging

**Files:**
- Modify: `src/cps/config.py`
- Modify: `src/cps/bot/messages.py`
- Modify: `src/cps/bot/keyboards.py`
- Modify: `tests/unit/test_keyboards.py`
- Modify: `tests/unit/test_config.py` (if it references demo_asin)

**Step 1: Update config.py**

- `demo_asin: str = Field(default="B0D1XD1ZV3", description="ASIN for ...")` → `demo_product_id: str = Field(default="B0D1XD1ZV3", description="Product ID for onboarding demo (pre-seeded in DB)")`
- Add: `demo_platform: str = Field(default="amazon", description="Platform for onboarding demo product")`

**Step 2: Update messages.py**

- `crawl_failed(self, asin: str)` → `crawl_failed(self, platform_id: str)` (line 113)
- Inside: `f"... for {asin}..."` → `f"... for {platform_id}..."`

**Step 3: Update keyboards.py**

All functions with `asin` parameter → `platform_id`:

- `build_price_report_keyboard(buy_url, asin, density)` → `build_price_report_keyboard(buy_url, platform_id, density)`
  - Callback data: `f"density:standard:{asin}"` → `f"density:standard:{platform_id}"` etc.
  - `f"alert:{asin}"` → `f"alert:{platform_id}"`
- `build_target_keyboard(asin, targets)` → `build_target_keyboard(platform_id, targets)`
  - `f"target:{asin}:{t['price']}"` → `f"target:{platform_id}:{t['price']}"`
  - `f"target_custom:{asin}"` → `f"target_custom:{platform_id}"`
  - `f"target:{asin}:skip"` → `f"target:{platform_id}:skip"`
- `build_monitor_item_keyboard(asin)` → `build_monitor_item_keyboard(platform_id)`
  - `f"view_detail:{asin}"` → `f"view_detail:{platform_id}"`
  - `f"remove_monitor:{asin}"` → `f"remove_monitor:{platform_id}"`
- `build_monitor_expiry_keyboard(asin)` → `build_monitor_expiry_keyboard(platform_id)`
  - Same pattern for callback data
- `build_deal_push_keyboard(buy_url, asin, category)` → `build_deal_push_keyboard(buy_url, platform_id, category)`
  - `f"dismiss_asin:{asin}"` → `f"dismiss_product:{platform_id}"`

**Step 4: Update test_keyboards.py**

- All `asin="B08N5WRWNW"` → `platform_id="B08N5WRWNW"`
- `build_price_report_keyboard(buy_url=..., asin=..., density=...)` → `build_price_report_keyboard(buy_url=..., platform_id=..., density=...)`
- `build_target_keyboard("B08N5WRWNW", targets)` → `build_target_keyboard("B08N5WRWNW", targets)`
- `build_deal_push_keyboard(buy_url=..., asin=..., category=...)` → `build_deal_push_keyboard(buy_url=..., platform_id=..., category=...)`

**Step 5: Run tests**

Run: `uv run pytest tests/unit/test_keyboards.py tests/unit/test_config.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/cps/config.py src/cps/bot/messages.py src/cps/bot/keyboards.py tests/unit/test_keyboards.py tests/unit/test_config.py
git commit -m "refactor: rename asin→platform_id in config, messages, keyboards"
```

---

### Task 9: Bot Handlers

**Files:**
- Modify: `src/cps/bot/handlers/price_check.py`
- Modify: `src/cps/bot/handlers/callbacks.py`
- Modify: `src/cps/bot/handlers/start.py`
- Modify: `src/cps/bot/handlers/monitors.py`

**Step 1: Update price_check.py**

- Import: `from cps.services.asin_parser import ...` → `from cps.services.product_id_parser import ...`
- `InputType.ASIN` → `InputType.PRODUCT_ID` (line 60)
- `if parsed.input_type in (InputType.URL, InputType.ASIN):` → `if parsed.input_type in (InputType.URL, InputType.PRODUCT_ID):`
- `parsed.asin` → `parsed.platform_id` (line 61)
- `_handle_asin_lookup(update, context, session, user, asin, settings)` → `_handle_product_lookup(update, context, session, user, platform_id, settings)`:
  - `Product.asin == asin` → `Product.platform_id == platform_id`
  - `Product(asin=asin)` → `Product(platform_id=platform_id)`
  - `product.title or product.asin` → `product.title or product.platform_id`
  - `build_product_link(product.asin, ...)` → `build_product_link(product.platform_id, ...)`
  - `build_price_report_keyboard(buy_url, product.asin, ...)` → `build_price_report_keyboard(buy_url, product.platform_id, ...)`
- In `_send_price_report()`:
  - `product.title or product.asin` → `product.title or product.platform_id`
  - `build_product_link(product.asin, ...)` → `build_product_link(product.platform_id, ...)`
  - `build_price_report_keyboard(buy_url, product.asin, ...)` → `build_price_report_keyboard(buy_url, product.platform_id, ...)`

**Step 2: Update callbacks.py**

- Docstring line 5: `dismiss_asin` → `dismiss_product`
- Route line 40: keep BOTH old and new prefixes for backward compatibility with already-delivered Telegram messages:
  `data.startswith("dismiss_cat:") or data.startswith("dismiss_asin:") or data.startswith("dismiss_product:")`
  (old `dismiss_asin:` buttons in users' chats will still work)
- All `Product.asin == asin` → `Product.platform_id == platform_id` (local var rename)
- Add callback validation helper at top of file:
```python
import re
_PLATFORM_ID_RE = re.compile(r"^[A-Za-z0-9]{1,30}$")

def _validate_callback_id(raw: str) -> str | None:
    """Validate platform_id from callback data. Returns None if invalid."""
    return raw if _PLATFORM_ID_RE.fullmatch(raw) else None
```
- In each handler that extracts a platform_id from callback data, add validation:
```python
platform_id = data.split(":")[1]
if not _validate_callback_id(platform_id):
    return
```
- In `_handle_density_toggle`: `asin = parts[2]` → `platform_id = parts[2]`, validate, then `Product.platform_id == platform_id`
- In `_handle_alert_setup`: same pattern with validation
- In `_handle_target_selection`: same pattern
- In `_handle_remove_monitor`: same pattern
- In `_handle_dismiss`: handle both `dismiss_asin:` and `dismiss_product:` prefixes, `DealDismissal(user_id=user.id, dismissed_platform_id=platform_id)`
- In `view_detail:` handler: same pattern

**Step 3: Update start.py**

- `demo_asin = settings.demo_asin` → `demo_product_id = settings.demo_product_id` (line 43)
- `Product.asin == demo_asin` → `Product.platform_id == demo_product_id` (line 46)
- `product.title or demo_asin` → `product.title or demo_product_id` (lines 70, 77)
- `build_product_link(demo_asin, ...)` → `build_product_link(demo_product_id, ...)`

**Step 4: Update monitors.py**

- `product.title or product.asin` → `product.title or product.platform_id` (line 47)
- `asin = product.asin if product else "?"` → `platform_id = product.platform_id if product else "?"` (line 68)
- `build_monitor_item_keyboard(asin)` → `build_monitor_item_keyboard(platform_id)` (line 69)
- `product.title or asin` → `product.title or platform_id` (line 70)

**Step 5: Commit**

```bash
git add src/cps/bot/handlers/
git commit -m "refactor: rename asin→platform_id in all bot handlers"
```

---

### Task 10: Jobs

**Files:**
- Modify: `src/cps/jobs/deal_scanner.py`
- Modify: `src/cps/jobs/price_checker.py`
- Modify: `src/cps/jobs/crawl_failure_notifier.py`

**Step 1: Update deal_scanner.py**

- `dismissed_asins = {d.dismissed_asin for d in dismissals if d.dismissed_asin}` → `dismissed_platform_ids = {d.dismissed_platform_id for d in dismissals if d.dismissed_platform_id}` (line 71)
- `DealService.filter_dismissed(all_deals, dismissed_cats, dismissed_asins)` → `DealService.filter_dismissed(all_deals, dismissed_cats, dismissed_platform_ids)` (line 84)
- `build_product_link(deal.asin, ...)` → `build_product_link(deal.platform_id, ...)` (line 91)
- `build_deal_push_keyboard(buy_url, deal.asin, deal.category)` → `build_deal_push_keyboard(buy_url, deal.platform_id, deal.category)` (line 102)

**Step 2: Update price_checker.py**

- `product.title or product.asin` → `product.title or product.platform_id` (line 103)
- `build_product_link(product.asin, ...)` → `build_product_link(product.platform_id, ...)` (line 110)

**Step 3: Update crawl_failure_notifier.py**

- `templates.crawl_failed(product.asin)` → `templates.crawl_failed(product.platform_id)` (line 46)

**Step 4: Commit**

```bash
git add src/cps/jobs/
git commit -m "refactor: rename asin→platform_id in jobs"
```

---

### Task 11: CLI

**Files:**
- Modify: `src/cps/cli.py`

**Step 1: Update CLI commands**

- `seed_add` command: `asin: str = typer.Argument(help="Single ASIN to add")` → `platform_id: str = typer.Argument(help="Single product ID to add")` (line 81)
  - `manager.add_single(asin)` → `manager.add_single(platform_id)` (line 94)
  - `typer.echo(f"Added {asin}")` → `typer.echo(f"Added {platform_id}")` (line 97)
  - `typer.echo(f"Skipped {asin} ...")` → `typer.echo(f"Skipped {platform_id} ...")` (line 99)
- `crawl_run`: `help="Max ASINs to crawl"` → `help="Max products to crawl"` (line 136)
- `crawl_status`: `from cps.db.models import ..., ExtractionRun, ...` → `..., FetchRun, ...` (line 180)
  - `("extraction_runs", ExtractionRun)` → `("fetch_runs", FetchRun)` (line 316 area)
  - `select(func.count()).select_from(ExtractionRun)` → `select(func.count()).select_from(FetchRun)` (lines 203-208)
  - `ExtractionRun.validation_passed` → `FetchRun.validation_passed`
- `db_stats`: same import/reference updates for `ExtractionRun` → `FetchRun`
- `extract_run`: `asin: str = typer.Option(...)` → `platform_id: str = typer.Option(..., "--platform-id", help="Product ID to re-extract")` (line 258)
  - Echo: `f"Re-extracting data for {asin}..."` → `f"Re-extracting data for {platform_id}..."`
- `extract_batch`: `help="Max ASINs to re-extract"` → `help="Max products to re-extract"`

**Step 2: Commit**

```bash
git add src/cps/cli.py
git commit -m "refactor: rename asin→platform_id, ExtractionRun→FetchRun in CLI"
```

---

### Task 12: Integration Tests

**Files:**
- Modify: `tests/integration/test_db_models.py`
- Modify: `tests/integration/test_pipeline.py`
- Modify: `tests/integration/test_auto_recovery.py`
- Modify: `tests/integration/test_crash_recovery.py`
- Modify: `tests/integration/test_monitor_repo.py`

**Step 1: Update test_db_models.py**

- Import: `ExtractionRun` → `FetchRun` (line 16)
- All `Product(asin="B...")` → `Product(platform_id="B...")`
- `product.asin` → `product.platform_id`
- Class `TestExtractionRunModel` → `TestFetchRunModel`
- `ExtractionRun(...)` → `FetchRun(...)`
- Test `test_asin_uniqueness` → `test_platform_id_uniqueness`:
  - Note: uniqueness is now compound `(platform, platform_id)`, not just `platform_id`. Two products with same `platform_id` but different `platform` should be allowed. Update test to verify:
    - Same platform + same platform_id → IntegrityError
    - Different platform + same platform_id → OK

```python
async def test_platform_id_uniqueness(self, db_session: AsyncSession):
    """Duplicate (platform, platform_id) raises IntegrityError."""
    p1 = Product(platform_id="B08N5WRWNW", platform="amazon")
    p2 = Product(platform_id="B08N5WRWNW", platform="amazon")
    db_session.add(p1)
    await db_session.flush()

    db_session.add(p2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
```

**Step 2: Update test_pipeline.py**

- Import: `ExtractionRun` → `FetchRun` (line 14)
- All `Product(asin="B...")` → `Product(platform_id="B...")`
- `select(ExtractionRun)` → `select(FetchRun)` (line 105)
- `select(func.count()).select_from(ExtractionRun)` → `select(func.count()).select_from(FetchRun)` (line 170)
- ASIN file content: unchanged (these are still valid platform_ids)
- Fixture `asin_file` → `platform_id_file` (rename)

**Step 3: Update test_auto_recovery.py**

- All `Product(asin=f"B0TST{i:04d}")` → `Product(platform_id=f"B0TST{i:04d}")` (lines 40, 71, 102)

**Step 4: Update test_crash_recovery.py**

- All `Product(asin=...)` → `Product(platform_id=...)`

**Step 5: Update test_monitor_repo.py**

- `Product(asin="B0TESTMON1")` → `Product(platform_id="B0TESTMON1")` (line 14)
- `Product(asin=f"B0LMT{i:05d}")` → `Product(platform_id=f"B0LMT{i:05d}")` (line 33)
- `Product(asin="B0LMTEXTRA")` → `Product(platform_id="B0LMTEXTRA")` (line 39)

**Step 6: Commit**

```bash
git add tests/integration/
git commit -m "refactor: rename asin→platform_id, ExtractionRun→FetchRun in integration tests"
```

---

### Task 13: Full Verification

**Step 1: Run full test suite**

Run: `uv run pytest -v --tb=short`
Expected: 247 tests passing (count may change slightly if new tests were added)

**Step 2: Check for any remaining `asin` references (comprehensive grep)**

```bash
# Variable names and attribute access (catches .asin, =asin, asin=, f"{asin}")
grep -rn '\basin\b' src/cps/ tests/ --include="*.py" | grep -v "__pycache__" | grep -v "alembic" | grep -v "dismiss_asin" | grep -v "_ASIN_PATTERN" | grep -v "_AMAZON_ASIN_PATTERN" | grep -v "asin_match"

# Class name
grep -rn "ExtractionRun" src/cps/ tests/ --include="*.py" | grep -v "__pycache__"

# Table name
grep -rn "extraction_runs" src/cps/ tests/ --include="*.py" | grep -v "__pycache__" | grep -v "alembic"

# Old column name
grep -rn "dismissed_asin" src/cps/ tests/ --include="*.py" | grep -v "__pycache__" | grep -v "alembic"

# Old import path
grep -rn "asin_parser" src/cps/ tests/ --include="*.py" | grep -v "__pycache__"
```

All should return ZERO results (except Alembic migration files and the regex pattern constants).

**Step 3: Verify FK references on partitioned table**

After applying migration to the test DB, verify that the FK on `price_history.extraction_id` correctly references the renamed `fetch_runs` table:

```bash
uv run python -c "
import asyncio
from cps.config import get_settings
from cps.db.session import create_session_factory
from sqlalchemy import text

async def check():
    s = get_settings()
    factory = create_session_factory(s.test_database_url)
    async with factory() as session:
        result = await session.execute(text('''
            SELECT conname, confrelid::regclass
            FROM pg_constraint
            WHERE conrelid = 'price_history'::regclass AND contype = 'f'
        '''))
        for row in result.all():
            print(f'Constraint: {row[0]} → {row[1]}')
            assert 'fetch_runs' in str(row[1]), f'FK still references old table: {row[1]}'
        print('FK verification passed')

asyncio.run(check())
"
```

**Step 4: Lint check**

Run: `uv run ruff check src/ tests/`
Expected: No new errors

**Step 5: Final commit (if any cleanup was needed)**

```bash
git add -A
git commit -m "fix: clean up remaining asin references after migration"
```

---

## Summary of All Changes

| Layer | Files Changed | Key Renames |
|-------|--------------|-------------|
| Migration | `alembic/versions/003_multi_platform.py` | New file |
| Models | `src/cps/db/models.py` | `Product.asin→platform_id`, `ExtractionRun→FetchRun`, `dismissed_asin→dismissed_platform_id` |
| Services | `product_id_parser.py` (renamed), `affiliate.py`, `deal_service.py` | `InputType.ASIN→PRODUCT_ID`, `Deal.asin→platform_id` |
| Crawler | `storage.py`, `downloader.py` | `save(asin=)→save(platform_id=)`, `download(asin=)→download(platform_id=)` |
| Pipeline | `orchestrator.py` | `ExtractionRun→FetchRun`, `asin→platform_id` in logs |
| Seeds | `manager.py` | `_validate_asin→_validate_platform_id`, `Product(asin=)→Product(platform_id=)` |
| Config | `config.py` | `demo_asin→demo_product_id`, add `demo_platform` |
| Bot | `keyboards.py`, `messages.py`, all handlers | `asin→platform_id` params, `dismiss_asin→dismiss_product` |
| Jobs | `deal_scanner.py`, `price_checker.py`, `crawl_failure_notifier.py` | `dismissed_asin→dismissed_platform_id`, `product.asin→product.platform_id` |
| CLI | `cli.py` | `ExtractionRun→FetchRun`, `asin→platform_id` |
| Tests | 15+ test files | Matching renames |

**New columns added to existing tables:**
- `products.platform` (VARCHAR(30), default 'amazon')
- `products.url` (TEXT, nullable)
- `products.is_active` (BOOLEAN, default true)
- `fetch_runs.platform` (VARCHAR(30), default 'amazon')
- `crawl_tasks.platform` (VARCHAR(30), default 'amazon')

**Gate:** `uv run pytest` green before proceeding to Phase 1B.
