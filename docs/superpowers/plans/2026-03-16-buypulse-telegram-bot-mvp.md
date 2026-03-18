# BuyPulse Phase 2: Telegram Bot MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot that lets US consumers monitor Amazon product prices and receive deal notifications, monetized via affiliate links.

**Architecture:** Extend the existing CPS Python codebase (Phase 1: CCC price data pipeline) with three new packages: `bot/` (Telegram interface), `services/` (business logic), `jobs/` (background tasks). Reuse the existing async SQLAlchemy stack, CCC pipeline, and PostgreSQL database. python-telegram-bot v21+ for Telegram, APScheduler for periodic jobs.

**Tech Stack:** python-telegram-bot v21+, APScheduler 3.x, existing SQLAlchemy 2.0 async, PostgreSQL, pytest + pytest-asyncio

**Key References:**
- Product design: `docs/superpowers/specs/2026-03-16-buypulse-product-design.md`
- Existing DB models: `src/cps/db/models.py`
- Existing config: `src/cps/config.py`
- Existing CLI: `src/cps/cli.py`

---

## File Structure

### New Files
```
src/cps/
├── bot/
│   ├── __init__.py          # Package init
│   ├── app.py               # Bot Application factory + runner
│   ├── handlers.py          # All command/message/callback handlers
│   ├── messages.py          # i18n message templates (EN + ES)
│   └── keyboards.py         # Inline keyboard builders
├── services/
│   ├── __init__.py          # Package init
│   ├── asin_parser.py       # Amazon URL → ASIN extraction
│   ├── price_analysis.py    # Price percentile, range position, "good price" logic
│   ├── affiliate.py         # Amazon affiliate link generation
│   └── notification.py      # Notification dispatcher (Telegram push)
├── jobs/
│   ├── __init__.py          # Package init
│   ├── price_checker.py     # Periodic: re-crawl monitored ASINs → check targets → notify
│   └── deal_scanner.py      # Periodic: detect category-wide deals → notify subscribers
tests/
├── unit/
│   ├── test_asin_parser.py
│   ├── test_price_analysis.py
│   ├── test_affiliate.py
│   ├── test_messages.py
│   ├── test_keyboards.py
│   ├── test_handlers.py
│   ├── test_notification.py
│   ├── test_price_checker.py
│   └── test_deal_scanner.py
├── integration/
│   ├── test_user_repo.py
│   ├── test_monitor_repo.py
│   └── test_bot_e2e.py
```

### Modified Files
```
src/cps/db/models.py         # Add 4 new tables: TelegramUser, PriceMonitor, CategorySubscription, NotificationLog
src/cps/config.py            # Add bot token, affiliate tag, job intervals
src/cps/cli.py               # Add `bot` command group
pyproject.toml               # Add python-telegram-bot, apscheduler dependencies
alembic/versions/002_user_layer.py  # New migration
```

---

## Chunk 1: Database Layer + Config

### Task 1: Add user-layer ORM models

**Files:**
- Modify: `src/cps/db/models.py`
- Test: `tests/unit/test_user_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_user_models.py
"""Unit tests for user-layer ORM models — schema validation only."""
from cps.db.models import (
    CategorySubscription,
    NotificationLog,
    PriceMonitor,
    TelegramUser,
)


class TestTelegramUser:
    def test_tablename(self):
        assert TelegramUser.__tablename__ == "telegram_users"

    def test_columns_exist(self):
        cols = {c.name for c in TelegramUser.__table__.columns}
        assert cols >= {
            "id", "telegram_id", "username", "first_name",
            "language", "timezone", "is_active", "monitor_limit",
            "created_at", "updated_at",
        }

    def test_telegram_id_unique(self):
        col = TelegramUser.__table__.c.telegram_id
        assert col.unique is True

    def test_language_default(self):
        col = TelegramUser.__table__.c.language
        assert col.server_default is not None


class TestPriceMonitor:
    def test_tablename(self):
        assert PriceMonitor.__tablename__ == "price_monitors"

    def test_columns_exist(self):
        cols = {c.name for c in PriceMonitor.__table__.columns}
        assert cols >= {
            "id", "user_id", "product_id", "target_price_cents",
            "is_active", "last_notified_at", "created_at", "updated_at",
        }

    def test_unique_user_product(self):
        indexes = PriceMonitor.__table__.indexes
        uq = [i for i in indexes if i.unique]
        assert len(uq) >= 1


class TestCategorySubscription:
    def test_tablename(self):
        assert CategorySubscription.__tablename__ == "category_subscriptions"

    def test_unique_user_category(self):
        indexes = CategorySubscription.__table__.indexes
        uq = [i for i in indexes if i.unique]
        assert len(uq) >= 1


class TestNotificationLog:
    def test_tablename(self):
        assert NotificationLog.__tablename__ == "notification_log"

    def test_columns_exist(self):
        cols = {c.name for c in NotificationLog.__table__.columns}
        assert cols >= {
            "id", "user_id", "product_id", "notification_type",
            "affiliate_tag", "clicked", "sent_at", "clicked_at",
        }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_user_models.py -v`
Expected: FAIL with ImportError (TelegramUser not defined)

- [ ] **Step 3: Write minimal implementation**

Add to `src/cps/db/models.py` after the existing `CrawlTask` class:

```python
class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(
        String(5), nullable=False, server_default="en"
    )
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="America/New_York"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    monitor_limit: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="20"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    monitors: Mapped[list["PriceMonitor"]] = relationship(back_populates="user")
    subscriptions: Mapped[list["CategorySubscription"]] = relationship(
        back_populates="user"
    )
    notifications: Mapped[list["NotificationLog"]] = relationship(
        back_populates="user"
    )


class PriceMonitor(Base):
    __tablename__ = "price_monitors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("telegram_users.id"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    target_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user: Mapped["TelegramUser"] = relationship(back_populates="monitors")
    product: Mapped["Product"] = relationship()

    __table_args__ = (
        Index("uq_monitor_user_product", "user_id", "product_id", unique=True),
        Index("idx_monitor_active", "is_active", postgresql_where="is_active = true"),
    )


class CategorySubscription(Base):
    __tablename__ = "category_subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("telegram_users.id"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user: Mapped["TelegramUser"] = relationship(back_populates="subscriptions")

    __table_args__ = (
        Index("uq_sub_user_category", "user_id", "category", unique=True),
    )


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("telegram_users.id"), nullable=False
    )
    product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=True
    )
    notification_type: Mapped[str] = mapped_column(String(20), nullable=False)
    affiliate_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    clicked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    clicked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["TelegramUser"] = relationship(back_populates="notifications")
    product: Mapped["Product | None"] = relationship()

    __table_args__ = (
        Index("idx_notif_user", "user_id"),
        Index("idx_notif_sent_at", "sent_at"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_user_models.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/db/models.py tests/unit/test_user_models.py
git commit -m "feat: add user-layer ORM models (TelegramUser, PriceMonitor, CategorySubscription, NotificationLog)"
```

---

### Task 2: Alembic migration for user-layer tables

**Files:**
- Create: `alembic/versions/002_user_layer.py`

- [ ] **Step 1: Generate migration**

Run: `uv run alembic revision -m "add user layer tables" --rev-id 002`

- [ ] **Step 2: Write migration content**

```python
"""add user layer tables

Revision ID: 002
Revises: 001
Create Date: 2026-03-16
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # telegram_users
    op.create_table(
        "telegram_users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("language", sa.String(5), nullable=False, server_default="en"),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="America/New_York"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("monitor_limit", sa.SmallInteger(), nullable=False, server_default="20"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )

    # price_monitors
    op.create_table(
        "price_monitors",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("target_price_cents", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["telegram_users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
    )
    op.create_index("uq_monitor_user_product", "price_monitors", ["user_id", "product_id"], unique=True)
    op.create_index("idx_monitor_active", "price_monitors", ["is_active"], postgresql_where=sa.text("is_active = true"))

    # category_subscriptions
    op.create_table(
        "category_subscriptions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["telegram_users.id"]),
    )
    op.create_index("uq_sub_user_category", "category_subscriptions", ["user_id", "category"], unique=True)

    # notification_log
    op.create_table(
        "notification_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("notification_type", sa.String(20), nullable=False),
        sa.Column("affiliate_tag", sa.String(100), nullable=True),
        sa.Column("clicked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["telegram_users.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
    )
    op.create_index("idx_notif_user", "notification_log", ["user_id"])
    op.create_index("idx_notif_sent_at", "notification_log", ["sent_at"])


def downgrade() -> None:
    op.drop_table("notification_log")
    op.drop_table("category_subscriptions")
    op.drop_table("price_monitors")
    op.drop_table("telegram_users")
```

- [ ] **Step 3: Run migration against dev DB**

Run: `uv run alembic upgrade head`
Expected: "Running upgrade 001 -> 002, add user layer tables"

- [ ] **Step 4: Verify tables exist**

Run: `docker exec cps-dev-db psql -U cps -d cps -c "\dt telegram_users; \dt price_monitors; \dt category_subscriptions; \dt notification_log;"`
Expected: 4 tables listed

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/002_user_layer.py
git commit -m "feat: add alembic migration 002 for user-layer tables"
```

---

### Task 3: Extend config with bot settings

**Files:**
- Modify: `src/cps/config.py`
- Test: `tests/unit/test_config.py` (extend existing)

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_config.py`:

```python
def test_bot_config_fields():
    """Bot-related settings should have sane defaults."""
    from cps.config import Settings
    fields = Settings.model_fields
    assert "telegram_bot_token" in fields
    assert "affiliate_tag" in fields
    assert "price_check_interval_hours" in fields
    assert "deal_scan_interval_hours" in fields


def test_affiliate_tag_default():
    import os
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://x:x@localhost/x"
    os.environ["TELEGRAM_BOT_TOKEN"] = "fake:token"
    from cps.config import Settings
    s = Settings()
    assert s.affiliate_tag == "buypulse-20"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py::test_bot_config_fields -v`
Expected: FAIL (field not found)

- [ ] **Step 3: Write minimal implementation**

Add to `src/cps/config.py` `Settings` class:

```python
    # Telegram Bot
    telegram_bot_token: str = Field(
        default="",
        description="Telegram Bot API token from @BotFather",
    )

    # Affiliate
    affiliate_tag: str = Field(
        default="buypulse-20",
        description="Amazon Associates affiliate tag",
    )

    # Background jobs
    price_check_interval_hours: int = Field(
        default=6,
        description="Hours between price check runs for monitored ASINs",
    )
    deal_scan_interval_hours: int = Field(
        default=12,
        description="Hours between deal scan runs",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/config.py tests/unit/test_config.py
git commit -m "feat: add bot and affiliate config settings"
```

---

### Task 4: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add new dependencies**

```bash
uv add "python-telegram-bot[job-queue]>=21.0"
```

Note: python-telegram-bot v21+ includes APScheduler via the `[job-queue]` extra, so no separate APScheduler dependency needed.

- [ ] **Step 2: Verify install**

Run: `uv run python -c "import telegram; print(telegram.__version__)"`
Expected: version 21.x printed

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add python-telegram-bot dependency"
```

---

## Chunk 2: Core Services

### Task 5: ASIN parser service

**Files:**
- Create: `src/cps/services/__init__.py`
- Create: `src/cps/services/asin_parser.py`
- Create: `tests/unit/test_asin_parser.py`

- [ ] **Step 1: Create package init**

```python
# src/cps/services/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_asin_parser.py
"""Tests for ASIN extraction from Amazon URLs and plain text."""
import pytest

from cps.services.asin_parser import extract_asin


@pytest.mark.parametrize(
    "text,expected",
    [
        # Standard product URLs
        ("https://www.amazon.com/dp/B08N5WRWNW", "B08N5WRWNW"),
        ("https://amazon.com/dp/B08N5WRWNW/ref=sr_1_1", "B08N5WRWNW"),
        ("https://www.amazon.com/gp/product/B09V3KXJPB", "B09V3KXJPB"),
        ("https://www.amazon.com/Some-Product-Name/dp/B0CJ4DKFRG/ref=sr", "B0CJ4DKFRG"),
        # Short URLs
        ("https://amzn.to/3xYz123", None),  # short URLs need redirect, return None
        ("https://a.co/d/abc1234", None),
        # Plain ASIN
        ("B08N5WRWNW", "B08N5WRWNW"),
        ("b08n5wrwnw", None),  # ASINs are uppercase
        # ASIN in message text
        ("Check this out: B08N5WRWNW it's great", "B08N5WRWNW"),
        ("Look at https://www.amazon.com/dp/B0CJ4DKFRG please", "B0CJ4DKFRG"),
        # Invalid
        ("hello world", None),
        ("https://google.com", None),
        ("", None),
        ("B08", None),  # too short
    ],
)
def test_extract_asin(text: str, expected: str | None):
    assert extract_asin(text) == expected
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_asin_parser.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 4: Write minimal implementation**

```python
# src/cps/services/asin_parser.py
"""Extract Amazon ASIN from URLs or plain text."""
import re

# Match ASIN in Amazon URL path: /dp/ASIN or /gp/product/ASIN
_URL_PATTERN = re.compile(
    r"amazon\.com(?:\.\w+)?/(?:dp|gp/product)/([A-Z0-9]{10})"
)

# Match standalone ASIN (10-char alphanumeric starting with B)
_PLAIN_PATTERN = re.compile(r"\b(B[A-Z0-9]{9})\b")


def extract_asin(text: str) -> str | None:
    """Extract an ASIN from an Amazon URL or plain text.

    Returns the ASIN string or None if not found.
    Short URLs (amzn.to, a.co) are not resolved — returns None.
    """
    if not text:
        return None

    # Try URL pattern first
    url_match = _URL_PATTERN.search(text)
    if url_match:
        return url_match.group(1)

    # Try plain ASIN pattern
    plain_match = _PLAIN_PATTERN.search(text)
    if plain_match:
        return plain_match.group(1)

    return None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_asin_parser.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/cps/services/__init__.py src/cps/services/asin_parser.py tests/unit/test_asin_parser.py
git commit -m "feat: add ASIN parser service for Amazon URL extraction"
```

---

### Task 6: Price analysis service

**Files:**
- Create: `src/cps/services/price_analysis.py`
- Create: `tests/unit/test_price_analysis.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_price_analysis.py
"""Tests for price analysis — percentile ranking and range position."""
from dataclasses import dataclass

import pytest

from cps.services.price_analysis import PriceReport, analyze_price


class TestAnalyzePrice:
    def test_basic_range(self):
        """Current price at midpoint of range."""
        report = analyze_price(
            current_cents=30000,
            lowest_cents=20000,
            highest_cents=40000,
        )
        assert report.current_cents == 30000
        assert report.lowest_cents == 20000
        assert report.highest_cents == 40000
        assert report.percentile == 50

    def test_at_lowest(self):
        report = analyze_price(
            current_cents=20000,
            lowest_cents=20000,
            highest_cents=40000,
        )
        assert report.percentile == 0
        assert report.verdict == "lowest"

    def test_at_highest(self):
        report = analyze_price(
            current_cents=40000,
            lowest_cents=20000,
            highest_cents=40000,
        )
        assert report.percentile == 100
        assert report.verdict == "highest"

    def test_lower_30(self):
        """Price in the lower 30% → verdict is 'good'."""
        report = analyze_price(
            current_cents=24000,  # 20% into range
            lowest_cents=20000,
            highest_cents=40000,
        )
        assert report.percentile == 20
        assert report.verdict == "good"

    def test_upper_70(self):
        """Price in upper 30% → verdict is 'high'."""
        report = analyze_price(
            current_cents=36000,  # 80% into range
            lowest_cents=20000,
            highest_cents=40000,
        )
        assert report.percentile == 80
        assert report.verdict == "high"

    def test_middle(self):
        """Price in the 30-70% range → verdict is 'average'."""
        report = analyze_price(
            current_cents=30000,  # 50%
            lowest_cents=20000,
            highest_cents=40000,
        )
        assert report.percentile == 50
        assert report.verdict == "average"

    def test_same_low_high(self):
        """When lowest == highest, percentile is 0."""
        report = analyze_price(
            current_cents=10000,
            lowest_cents=10000,
            highest_cents=10000,
        )
        assert report.percentile == 0

    def test_format_price(self):
        report = analyze_price(
            current_cents=31999,
            lowest_cents=24900,
            highest_cents=42900,
        )
        assert report.current_display == "$319.99"
        assert report.lowest_display == "$249.00"
        assert report.highest_display == "$429.00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_price_analysis.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write minimal implementation**

```python
# src/cps/services/price_analysis.py
"""Price analysis — percentile ranking and range position."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PriceReport:
    """Immutable price analysis result."""

    current_cents: int
    lowest_cents: int
    highest_cents: int
    percentile: int  # 0-100, where 0 = at lowest, 100 = at highest
    verdict: str  # "lowest", "good", "average", "high", "highest"

    @property
    def current_display(self) -> str:
        return _fmt(self.current_cents)

    @property
    def lowest_display(self) -> str:
        return _fmt(self.lowest_cents)

    @property
    def highest_display(self) -> str:
        return _fmt(self.highest_cents)


def _fmt(cents: int) -> str:
    """Format cents as dollar string."""
    return f"${cents / 100:.2f}"


def analyze_price(
    current_cents: int,
    lowest_cents: int,
    highest_cents: int,
) -> PriceReport:
    """Analyze current price position within historical range.

    Returns an immutable PriceReport with percentile and verdict.
    """
    price_range = highest_cents - lowest_cents
    if price_range == 0:
        percentile = 0
    else:
        percentile = round((current_cents - lowest_cents) / price_range * 100)
        percentile = max(0, min(100, percentile))

    if percentile == 0:
        verdict = "lowest"
    elif percentile <= 30:
        verdict = "good"
    elif percentile < 70:
        verdict = "average"
    elif percentile < 100:
        verdict = "high"
    else:
        verdict = "highest"

    return PriceReport(
        current_cents=current_cents,
        lowest_cents=lowest_cents,
        highest_cents=highest_cents,
        percentile=percentile,
        verdict=verdict,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_price_analysis.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/services/price_analysis.py tests/unit/test_price_analysis.py
git commit -m "feat: add price analysis service with percentile ranking"
```

---

### Task 7: Affiliate link service

**Files:**
- Create: `src/cps/services/affiliate.py`
- Create: `tests/unit/test_affiliate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_affiliate.py
"""Tests for Amazon affiliate link generation."""
from cps.services.affiliate import build_affiliate_link


def test_basic_link():
    url = build_affiliate_link("B08N5WRWNW", tag="buypulse-20")
    assert url == "https://www.amazon.com/dp/B08N5WRWNW?tag=buypulse-20"


def test_different_tag():
    url = build_affiliate_link("B09V3KXJPB", tag="custom-21")
    assert url == "https://www.amazon.com/dp/B09V3KXJPB?tag=custom-21"


def test_tag_is_required():
    """Tag must be explicitly passed — no hidden default."""
    import pytest
    with pytest.raises(TypeError):
        build_affiliate_link("B08N5WRWNW")  # Missing required 'tag'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_affiliate.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write minimal implementation**

```python
# src/cps/services/affiliate.py
"""Amazon affiliate link generation."""


def build_affiliate_link(asin: str, *, tag: str) -> str:
    """Build an Amazon product URL with affiliate tag.

    The tag parameter is required — callers must pass it from config
    to avoid hardcoded defaults drifting from settings.
    """
    return f"https://www.amazon.com/dp/{asin}?tag={tag}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_affiliate.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/services/affiliate.py tests/unit/test_affiliate.py
git commit -m "feat: add affiliate link service"
```

---

### Task 8: i18n message templates

**Files:**
- Create: `src/cps/bot/__init__.py`
- Create: `src/cps/bot/messages.py`
- Create: `tests/unit/test_messages.py`

- [ ] **Step 1: Create package init**

```python
# src/cps/bot/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_messages.py
"""Tests for i18n message templates."""
from cps.bot.messages import msg


class TestMsg:
    def test_welcome_en(self):
        text = msg("welcome", lang="en")
        assert "BuyPulse" in text
        assert "Amazon" in text

    def test_welcome_es(self):
        text = msg("welcome", lang="es")
        assert "BuyPulse" in text
        # Spanish text should be different from English
        assert "Bienvenido" in text or "monitor" in text.lower()

    def test_unknown_key(self):
        text = msg("nonexistent_key", lang="en")
        assert text == "[nonexistent_key]"

    def test_unknown_lang_falls_back_to_en(self):
        text = msg("welcome", lang="fr")
        assert "BuyPulse" in text  # falls back to English

    def test_template_variables(self):
        text = msg("price_report", lang="en", product="AirPods", current="$199", low="$149", high="$249", percentile="30", verdict="good")
        assert "AirPods" in text
        assert "$199" in text
        assert "$149" in text

    def test_price_report_es(self):
        text = msg("price_report", lang="es", product="AirPods", current="$199", low="$149", high="$249", percentile="30", verdict="bueno")
        assert "AirPods" in text
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_messages.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 4: Write minimal implementation**

```python
# src/cps/bot/messages.py
"""i18n message templates — English + Spanish."""

_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "welcome": (
            "Welcome to BuyPulse! I help you find the best time to buy on Amazon.\n\n"
            "Send me an Amazon product link or ASIN to get started.\n\n"
            "Commands:\n"
            "/monitors - View your watched items\n"
            "/subscribe - Subscribe to deal categories\n"
            "/language - Change language\n"
            "/help - Show help"
        ),
        "help": (
            "How to use BuyPulse:\n\n"
            "1. Send me an Amazon link or ASIN\n"
            "2. I'll show you the price history\n"
            "3. Set a target price to get notified\n\n"
            "Commands:\n"
            "/monitors - Your watched items ({count}/{limit})\n"
            "/subscribe - Deal category subscriptions\n"
            "/language - Change language\n"
            "/help - This message"
        ),
        "price_report": (
            "{product}\n"
            "Current: {current}\n"
            "Historical: {low} - {high}\n"
            "This price is in the lower {percentile}% of its range ({verdict}).\n\n"
            "Set a target price to get notified when it drops?"
        ),
        "target_set": "Done! Watching {product}. I'll notify you when it drops to {target} or below.",
        "target_prompt": "What's your target price? (e.g. $280 or 280)",
        "monitor_limit": "You've reached your monitor limit ({limit} items). Remove one first with /monitors.",
        "price_alert": (
            "Price drop! {product} is now {current}\n"
            "Your target: {target}\n"
            "Historical low: {low}\n"
            "[Buy on Amazon]({link})"
        ),
        "deal_push": (
            "Deal in {category}:\n"
            "{product} dropped to {current} (was {previous})\n"
            "{context}\n"
            "[Buy on Amazon]({link})"
        ),
        "no_monitors": "You have no active monitors. Send me an Amazon link to start!",
        "monitor_list_header": "Your monitors ({count}/{limit}):",
        "monitor_item": "{idx}. {product} — target: {target}",
        "monitor_removed": "Removed {product} from your monitors.",
        "subscribe_prompt": "Select categories to get deal alerts:",
        "subscribed": "Subscribed to {category}!",
        "unsubscribed": "Unsubscribed from {category}.",
        "language_changed": "Language changed to English.",
        "product_not_found": "I couldn't find price data for this product. I'll try to fetch it — check back in a few minutes.",
        "invalid_input": "I didn't understand that. Send me an Amazon link, ASIN, or use /help.",
        "error": "Something went wrong. Please try again.",
    },
    "es": {
        "welcome": (
            "Bienvenido a BuyPulse! Te ayudo a encontrar el mejor momento para comprar en Amazon.\n\n"
            "Envíame un enlace de Amazon o un ASIN para empezar.\n\n"
            "Comandos:\n"
            "/monitors - Ver tus productos monitoreados\n"
            "/subscribe - Suscribirte a categorías de ofertas\n"
            "/language - Cambiar idioma\n"
            "/help - Mostrar ayuda"
        ),
        "help": (
            "Cómo usar BuyPulse:\n\n"
            "1. Envíame un enlace de Amazon o ASIN\n"
            "2. Te mostraré el historial de precios\n"
            "3. Establece un precio objetivo para recibir notificaciones\n\n"
            "Comandos:\n"
            "/monitors - Tus productos monitoreados ({count}/{limit})\n"
            "/subscribe - Suscripciones a categorías\n"
            "/language - Cambiar idioma\n"
            "/help - Este mensaje"
        ),
        "price_report": (
            "{product}\n"
            "Actual: {current}\n"
            "Histórico: {low} - {high}\n"
            "Este precio está en el {percentile}% inferior de su rango ({verdict}).\n\n"
            "¿Establecer un precio objetivo para recibir notificaciones?"
        ),
        "target_set": "¡Listo! Monitoreando {product}. Te avisaré cuando baje a {target} o menos.",
        "target_prompt": "¿Cuál es tu precio objetivo? (ej. $280 o 280)",
        "monitor_limit": "Has alcanzado tu límite de monitores ({limit} productos). Elimina uno primero con /monitors.",
        "price_alert": (
            "¡Bajó de precio! {product} ahora está a {current}\n"
            "Tu objetivo: {target}\n"
            "Mínimo histórico: {low}\n"
            "[Comprar en Amazon]({link})"
        ),
        "deal_push": (
            "Oferta en {category}:\n"
            "{product} bajó a {current} (antes {previous})\n"
            "{context}\n"
            "[Comprar en Amazon]({link})"
        ),
        "no_monitors": "No tienes monitores activos. ¡Envíame un enlace de Amazon para empezar!",
        "monitor_list_header": "Tus monitores ({count}/{limit}):",
        "monitor_item": "{idx}. {product} — objetivo: {target}",
        "monitor_removed": "{product} eliminado de tus monitores.",
        "subscribe_prompt": "Selecciona categorías para recibir alertas:",
        "subscribed": "¡Suscrito a {category}!",
        "unsubscribed": "Desuscrito de {category}.",
        "language_changed": "Idioma cambiado a Español.",
        "product_not_found": "No encontré datos de precio para este producto. Intentaré obtenerlos — vuelve en unos minutos.",
        "invalid_input": "No entendí eso. Envíame un enlace de Amazon, ASIN, o usa /help.",
        "error": "Algo salió mal. Por favor intenta de nuevo.",
    },
}


def msg(key: str, *, lang: str = "en", **kwargs: str) -> str:
    """Get a localized message template, formatted with kwargs.

    Falls back to English if the language or key is not found.
    Returns '[key]' if the key doesn't exist in any language.
    """
    templates = _TEMPLATES.get(lang, _TEMPLATES["en"])
    template = templates.get(key)
    if template is None:
        # Fallback to English
        template = _TEMPLATES["en"].get(key)
    if template is None:
        return f"[{key}]"
    if kwargs:
        return template.format(**kwargs)
    return template
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_messages.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/cps/bot/__init__.py src/cps/bot/messages.py tests/unit/test_messages.py
git commit -m "feat: add i18n message templates (English + Spanish)"
```

---

### Task 9: Inline keyboard builders

**Files:**
- Create: `src/cps/bot/keyboards.py`
- Create: `tests/unit/test_keyboards.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_keyboards.py
"""Tests for inline keyboard builders."""
from cps.bot.keyboards import (
    build_category_keyboard,
    build_monitor_list_keyboard,
    build_target_confirm_keyboard,
    build_language_keyboard,
    CATEGORIES,
)


class TestCategoryKeyboard:
    def test_returns_list_of_rows(self):
        kb = build_category_keyboard(subscribed=set())
        assert len(kb) > 0
        # Each row is a list of InlineKeyboardButton
        for row in kb:
            assert len(row) >= 1

    def test_subscribed_marked(self):
        kb = build_category_keyboard(subscribed={"Electronics"})
        # Find the Electronics button — should have a checkmark
        found = False
        for row in kb:
            for btn in row:
                if "Electronics" in btn.text:
                    assert "✓" in btn.text or "✅" in btn.text
                    found = True
        assert found


class TestTargetConfirmKeyboard:
    def test_has_yes_no(self):
        kb = build_target_confirm_keyboard(lang="en")
        texts = [btn.text for row in kb for btn in row]
        assert any("Yes" in t for t in texts)
        assert any("No" in t or "Skip" in t for t in texts)


class TestLanguageKeyboard:
    def test_has_en_es(self):
        kb = build_language_keyboard()
        texts = [btn.text for row in kb for btn in row]
        assert any("English" in t for t in texts)
        assert any("Español" in t for t in texts)


class TestMonitorListKeyboard:
    def test_empty_list(self):
        kb = build_monitor_list_keyboard(monitors=[])
        assert kb == []

    def test_with_monitors(self):
        monitors = [
            {"id": 1, "product_name": "AirPods", "target": "$199"},
            {"id": 2, "product_name": "iPad", "target": "$449"},
        ]
        kb = build_monitor_list_keyboard(monitors=monitors)
        assert len(kb) == 2
        # Each button should have remove callback data
        for row in kb:
            assert row[0].callback_data.startswith("rm_")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_keyboards.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write minimal implementation**

```python
# src/cps/bot/keyboards.py
"""Inline keyboard builders for the Telegram bot."""
from telegram import InlineKeyboardButton

CATEGORIES = [
    "Electronics",
    "Computers",
    "Home & Kitchen",
    "Sports & Outdoors",
    "Tools & Home Improvement",
    "Toys & Games",
    "Beauty & Personal Care",
    "Health & Household",
    "Automotive",
    "Pet Supplies",
]


def build_category_keyboard(
    *, subscribed: set[str]
) -> list[list[InlineKeyboardButton]]:
    """Build category selection keyboard. Subscribed categories show a checkmark."""
    rows: list[list[InlineKeyboardButton]] = []
    for cat in CATEGORIES:
        prefix = "✅ " if cat in subscribed else ""
        action = "unsub" if cat in subscribed else "sub"
        rows.append([
            InlineKeyboardButton(
                text=f"{prefix}{cat}",
                callback_data=f"{action}_{cat}",
            )
        ])
    rows.append([InlineKeyboardButton(text="Done", callback_data="sub_done")])
    return rows


def build_target_confirm_keyboard(
    *, lang: str = "en"
) -> list[list[InlineKeyboardButton]]:
    """Build Yes/Skip keyboard for target price confirmation."""
    if lang == "es":
        return [[
            InlineKeyboardButton(text="Sí", callback_data="target_yes"),
            InlineKeyboardButton(text="Saltar", callback_data="target_skip"),
        ]]
    return [[
        InlineKeyboardButton(text="Yes", callback_data="target_yes"),
        InlineKeyboardButton(text="Skip", callback_data="target_skip"),
    ]]


def build_language_keyboard() -> list[list[InlineKeyboardButton]]:
    """Build language selection keyboard."""
    return [[
        InlineKeyboardButton(text="English", callback_data="lang_en"),
        InlineKeyboardButton(text="Español", callback_data="lang_es"),
    ]]


def build_monitor_list_keyboard(
    *, monitors: list[dict]
) -> list[list[InlineKeyboardButton]]:
    """Build monitor list with remove buttons."""
    rows: list[list[InlineKeyboardButton]] = []
    for m in monitors:
        rows.append([
            InlineKeyboardButton(
                text=f"❌ {m['product_name']} ({m['target']})",
                callback_data=f"rm_{m['id']}",
            )
        ])
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_keyboards.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/bot/keyboards.py tests/unit/test_keyboards.py
git commit -m "feat: add inline keyboard builders for bot UI"
```

---

## Chunk 3: Telegram Bot Handlers

### Task 10: Bot application factory

**Files:**
- Create: `src/cps/bot/app.py`
- Create: `tests/unit/test_bot_app.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_bot_app.py
"""Tests for bot application factory."""
from unittest.mock import patch

from cps.bot.app import create_bot_app


def test_create_bot_app_returns_application():
    """Factory should return a telegram Application instance."""
    with patch("cps.bot.app.ApplicationBuilder") as mock_builder:
        mock_app = mock_builder.return_value.token.return_value.build.return_value
        app = create_bot_app(token="fake:token", db_url="postgresql+asyncpg://x:x@localhost/x")
        assert app is mock_app


def test_create_bot_app_registers_handlers():
    """Factory should register at least start, help, and message handlers."""
    with patch("cps.bot.app.ApplicationBuilder") as mock_builder:
        mock_app = mock_builder.return_value.token.return_value.build.return_value
        create_bot_app(token="fake:token", db_url="postgresql+asyncpg://x:x@localhost/x")
        # At least some handlers should be added
        assert mock_app.add_handler.call_count >= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_bot_app.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write minimal implementation**

```python
# src/cps/bot/app.py
"""Telegram bot application factory."""
import structlog
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from cps.bot.handlers import (
    handle_callback,
    handle_help,
    handle_language,
    handle_message,
    handle_monitors,
    handle_start,
    handle_subscribe,
    handle_target_price,
    WAITING_TARGET,
)
from cps.db.session import create_session_factory

log = structlog.get_logger()


def create_bot_app(
    *,
    token: str,
    db_url: str,
    affiliate_tag: str = "buypulse-20",
    price_check_interval_hours: int = 6,
    deal_scan_interval_hours: int = 12,
) -> Application:
    """Create and configure the Telegram bot Application."""
    app = ApplicationBuilder().token(token).build()

    # Store shared state in bot_data
    app.bot_data["session_factory"] = create_session_factory(db_url)
    app.bot_data["affiliate_tag"] = affiliate_tag

    # Conversation handler for target price flow
    target_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern="^target_yes$")],
        states={
            WAITING_TARGET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_target_price),
            ],
        },
        fallbacks=[CommandHandler("cancel", handle_start)],
    )

    # Register handlers (order matters — first match wins)
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("monitors", handle_monitors))
    app.add_handler(CommandHandler("subscribe", handle_subscribe))
    app.add_handler(CommandHandler("language", handle_language))
    app.add_handler(target_conv)
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("bot_configured", handlers=app.handlers)
    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_bot_app.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/bot/app.py tests/unit/test_bot_app.py
git commit -m "feat: add bot application factory with handler registration"
```

---

### Task 11: Bot handlers — core logic

**Files:**
- Create: `src/cps/bot/handlers.py`
- Create: `tests/unit/test_handlers.py`

This is the largest task. It implements all user-facing bot interactions.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_handlers.py
"""Tests for Telegram bot handlers — uses mocked Update/Context."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.bot.handlers import (
    handle_start,
    handle_help,
    handle_message,
    _get_or_create_user,
    _parse_price_input,
)


class TestParsePrice:
    def test_dollar_sign(self):
        assert _parse_price_input("$280") == 28000

    def test_plain_number(self):
        assert _parse_price_input("280") == 28000

    def test_decimal(self):
        assert _parse_price_input("$279.99") == 27999

    def test_with_comma(self):
        assert _parse_price_input("$1,299") == 129900

    def test_invalid(self):
        assert _parse_price_input("hello") is None

    def test_zero(self):
        assert _parse_price_input("0") is None

    def test_negative(self):
        assert _parse_price_input("-50") is None


class TestHandleStart:
    @pytest.mark.asyncio
    async def test_sends_welcome(self):
        update = MagicMock()
        update.effective_user.id = 123
        update.effective_user.username = "testuser"
        update.effective_user.first_name = "Test"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.bot_data = {
            "session_factory": MagicMock(),
            "affiliate_tag": "test-20",
        }

        with patch("cps.bot.handlers._get_or_create_user", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MagicMock(language="en")
            await handle_start(update, context)

        update.message.reply_text.assert_called_once()
        call_text = update.message.reply_text.call_args[0][0]
        assert "BuyPulse" in call_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_handlers.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write minimal implementation**

```python
# src/cps/bot/handlers.py
"""Telegram bot command and message handlers."""
import re

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from cps.bot.keyboards import (
    build_category_keyboard,
    build_language_keyboard,
    build_monitor_list_keyboard,
    build_target_confirm_keyboard,
)
from cps.bot.messages import msg
from cps.db.models import (
    CategorySubscription,
    PriceMonitor,
    PriceSummary,
    Product,
    TelegramUser,
)
from cps.services.affiliate import build_affiliate_link
from cps.services.asin_parser import extract_asin
from cps.services.price_analysis import analyze_price

log = structlog.get_logger()

# ConversationHandler states
WAITING_TARGET = 1

# Price input regex
_PRICE_RE = re.compile(r"^\$?([\d,]+(?:\.\d{1,2})?)$")


def _parse_price_input(text: str) -> int | None:
    """Parse user price input to cents. Returns None if invalid."""
    text = text.strip()
    match = _PRICE_RE.match(text)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
        if value <= 0:
            return None
        return int(round(value * 100))
    except (ValueError, OverflowError):
        return None


async def _get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> TelegramUser:
    """Get existing user or create new one."""
    result = await session.execute(
        select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = TelegramUser(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        session.add(user)
        await session.flush()
        log.info("user_created", telegram_id=telegram_id)
    else:
        # Update username/first_name if changed
        if username and user.username != username:
            user.username = username
        if first_name and user.first_name != first_name:
            user.first_name = first_name
        await session.flush()
    return user


def _session_factory(context: ContextTypes.DEFAULT_TYPE) -> async_sessionmaker:
    return context.bot_data["session_factory"]


def _affiliate_tag(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.bot_data.get("affiliate_tag", "buypulse-20")


async def handle_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /start command — welcome message."""
    factory = _session_factory(context)
    async with factory() as session:
        user = await _get_or_create_user(
            session,
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        await session.commit()
        lang = user.language

    await update.message.reply_text(msg("welcome", lang=lang))


async def handle_help(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /help command."""
    factory = _session_factory(context)
    async with factory() as session:
        user = await _get_or_create_user(
            session, telegram_id=update.effective_user.id,
        )
        # Count monitors before commit
        result = await session.execute(
            select(PriceMonitor)
            .where(PriceMonitor.user_id == user.id, PriceMonitor.is_active == True)
        )
        count = len(result.scalars().all())
        lang = user.language
        limit = user.monitor_limit
        await session.commit()

    await update.message.reply_text(
        msg("help", lang=lang, count=str(count), limit=str(limit))
    )


async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int | None:
    """Handle plain text messages — try to extract ASIN."""
    text = update.message.text or ""
    asin = extract_asin(text)

    if asin is None:
        factory = _session_factory(context)
        async with factory() as session:
            user = await _get_or_create_user(
                session, telegram_id=update.effective_user.id,
            )
            await session.commit()
        await update.message.reply_text(msg("invalid_input", lang=user.language))
        return None

    # Look up price data
    factory = _session_factory(context)
    async with factory() as session:
        user = await _get_or_create_user(
            session, telegram_id=update.effective_user.id,
        )

        # Find product
        result = await session.execute(
            select(Product).where(Product.asin == asin)
        )
        product = result.scalar_one_or_none()

        if product is None:
            # Create product + crawl task so background job picks it up
            product = Product(asin=asin)
            session.add(product)
            await session.flush()

            from cps.db.models import CrawlTask
            task = CrawlTask(product_id=product.id, priority=1)  # High priority
            session.add(task)
            await session.commit()

            await update.message.reply_text(
                msg("product_not_found", lang=user.language)
            )
            log.info("on_demand_crawl_queued", asin=asin, product_id=product.id)
            return None

        # Get price summary (amazon-new type preferred)
        result = await session.execute(
            select(PriceSummary)
            .where(PriceSummary.product_id == product.id)
            .order_by(PriceSummary.updated_at.desc())
        )
        summary = result.scalar_one_or_none()

        if summary is None or summary.current_price is None:
            await update.message.reply_text(
                msg("product_not_found", lang=user.language)
            )
            await session.commit()
            return None

        # Analyze price
        report = analyze_price(
            current_cents=summary.current_price,
            lowest_cents=summary.lowest_price or summary.current_price,
            highest_cents=summary.highest_price or summary.current_price,
        )

        # Store ASIN in user_data for target price flow
        context.user_data["pending_asin"] = asin
        context.user_data["pending_product_id"] = product.id
        context.user_data["pending_product_name"] = product.title or asin

        await session.commit()

    # Send price report with target price question
    await update.message.reply_text(
        msg(
            "price_report",
            lang=user.language,
            product=product.title or asin,
            current=report.current_display,
            low=report.lowest_display,
            high=report.highest_display,
            percentile=str(report.percentile),
            verdict=report.verdict,
        ),
        reply_markup=InlineKeyboardMarkup(
            build_target_confirm_keyboard(lang=user.language)
        ),
    )
    return None


async def handle_target_price(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle target price input in conversation."""
    text = update.message.text or ""
    price_cents = _parse_price_input(text)

    factory = _session_factory(context)
    async with factory() as session:
        user = await _get_or_create_user(
            session, telegram_id=update.effective_user.id,
        )

        if price_cents is None:
            await update.message.reply_text(
                msg("target_prompt", lang=user.language)
            )
            return WAITING_TARGET

        product_id = context.user_data.get("pending_product_id")
        product_name = context.user_data.get("pending_product_name", "Unknown")

        if product_id is None:
            await update.message.reply_text(msg("error", lang=user.language))
            await session.commit()
            return ConversationHandler.END

        # Check monitor limit
        result = await session.execute(
            select(PriceMonitor)
            .where(PriceMonitor.user_id == user.id, PriceMonitor.is_active == True)
        )
        current_count = len(result.scalars().all())
        if current_count >= user.monitor_limit:
            await update.message.reply_text(
                msg("monitor_limit", lang=user.language, limit=str(user.monitor_limit))
            )
            await session.commit()
            return ConversationHandler.END

        # Create or update monitor
        result = await session.execute(
            select(PriceMonitor).where(
                PriceMonitor.user_id == user.id,
                PriceMonitor.product_id == product_id,
            )
        )
        monitor = result.scalar_one_or_none()
        if monitor is None:
            monitor = PriceMonitor(
                user_id=user.id,
                product_id=product_id,
                target_price_cents=price_cents,
            )
            session.add(monitor)
        else:
            monitor.target_price_cents = price_cents
            monitor.is_active = True

        await session.commit()

    target_display = f"${price_cents / 100:.2f}"
    await update.message.reply_text(
        msg("target_set", lang=user.language, product=product_name, target=target_display)
    )

    # Clean up user_data
    context.user_data.pop("pending_asin", None)
    context.user_data.pop("pending_product_id", None)
    context.user_data.pop("pending_product_name", None)

    return ConversationHandler.END


async def handle_monitors(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /monitors command — list active monitors with remove buttons."""
    factory = _session_factory(context)
    async with factory() as session:
        user = await _get_or_create_user(
            session, telegram_id=update.effective_user.id,
        )
        result = await session.execute(
            select(PriceMonitor, Product)
            .join(Product, PriceMonitor.product_id == Product.id)
            .where(PriceMonitor.user_id == user.id, PriceMonitor.is_active == True)
        )
        rows = result.all()
        await session.commit()

    if not rows:
        await update.message.reply_text(msg("no_monitors", lang=user.language))
        return

    monitors = []
    for monitor, product in rows:
        target = f"${monitor.target_price_cents / 100:.2f}" if monitor.target_price_cents else "no target"
        monitors.append({
            "id": monitor.id,
            "product_name": product.title or product.asin,
            "target": target,
        })

    text = msg(
        "monitor_list_header",
        lang=user.language,
        count=str(len(monitors)),
        limit=str(user.monitor_limit),
    )
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(build_monitor_list_keyboard(monitors=monitors)),
    )


async def handle_subscribe(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /subscribe command — show category selection keyboard."""
    factory = _session_factory(context)
    async with factory() as session:
        user = await _get_or_create_user(
            session, telegram_id=update.effective_user.id,
        )
        result = await session.execute(
            select(CategorySubscription.category)
            .where(
                CategorySubscription.user_id == user.id,
                CategorySubscription.is_active == True,
            )
        )
        subscribed = {row[0] for row in result.all()}
        await session.commit()

    await update.message.reply_text(
        msg("subscribe_prompt", lang=user.language),
        reply_markup=InlineKeyboardMarkup(
            build_category_keyboard(subscribed=subscribed)
        ),
    )


async def handle_language(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /language command — show language selection."""
    await update.message.reply_text(
        "Choose language / Elige idioma:",
        reply_markup=InlineKeyboardMarkup(build_language_keyboard()),
    )


async def handle_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int | None:
    """Handle all inline keyboard callback queries."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    factory = _session_factory(context)

    # Target price flow
    if data == "target_yes":
        async with factory() as session:
            user = await _get_or_create_user(
                session, telegram_id=update.effective_user.id,
            )
            await session.commit()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(msg("target_prompt", lang=user.language))
        return WAITING_TARGET

    if data == "target_skip":
        # Add monitor without target price
        async with factory() as session:
            user = await _get_or_create_user(
                session, telegram_id=update.effective_user.id,
            )
            product_id = context.user_data.get("pending_product_id")
            if product_id:
                result = await session.execute(
                    select(PriceMonitor).where(
                        PriceMonitor.user_id == user.id,
                        PriceMonitor.product_id == product_id,
                    )
                )
                monitor = result.scalar_one_or_none()
                if monitor is None:
                    monitor = PriceMonitor(
                        user_id=user.id,
                        product_id=product_id,
                    )
                    session.add(monitor)
                await session.commit()
        await query.edit_message_reply_markup(reply_markup=None)
        context.user_data.pop("pending_asin", None)
        context.user_data.pop("pending_product_id", None)
        context.user_data.pop("pending_product_name", None)
        return ConversationHandler.END

    # Monitor removal
    if data.startswith("rm_"):
        monitor_id = int(data[3:])
        async with factory() as session:
            user = await _get_or_create_user(
                session, telegram_id=update.effective_user.id,
            )
            result = await session.execute(
                select(PriceMonitor)
                .join(Product, PriceMonitor.product_id == Product.id)
                .where(PriceMonitor.id == monitor_id, PriceMonitor.user_id == user.id)
            )
            monitor = result.scalar_one_or_none()
            if monitor:
                monitor.is_active = False
                await session.commit()
                product = await session.get(Product, monitor.product_id)
                name = product.title or product.asin if product else "item"
                await query.edit_message_text(
                    msg("monitor_removed", lang=user.language, product=name)
                )
            else:
                await session.commit()
        return None

    # Category subscribe/unsubscribe
    if data.startswith("sub_") and data != "sub_done":
        category = data[4:]
        async with factory() as session:
            user = await _get_or_create_user(
                session, telegram_id=update.effective_user.id,
            )
            result = await session.execute(
                select(CategorySubscription).where(
                    CategorySubscription.user_id == user.id,
                    CategorySubscription.category == category,
                )
            )
            sub = result.scalar_one_or_none()
            if sub is None:
                sub = CategorySubscription(user_id=user.id, category=category)
                session.add(sub)
            else:
                sub.is_active = True
            await session.commit()
            await query.message.reply_text(
                msg("subscribed", lang=user.language, category=category)
            )
        return None

    if data.startswith("unsub_"):
        category = data[6:]
        async with factory() as session:
            user = await _get_or_create_user(
                session, telegram_id=update.effective_user.id,
            )
            result = await session.execute(
                select(CategorySubscription).where(
                    CategorySubscription.user_id == user.id,
                    CategorySubscription.category == category,
                )
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.is_active = False
                await session.commit()
            await query.message.reply_text(
                msg("unsubscribed", lang=user.language, category=category)
            )
        return None

    if data == "sub_done":
        await query.edit_message_reply_markup(reply_markup=None)
        return None

    # Language change
    if data.startswith("lang_"):
        new_lang = data[5:]
        async with factory() as session:
            user = await _get_or_create_user(
                session, telegram_id=update.effective_user.id,
            )
            user.language = new_lang
            await session.commit()
        await query.edit_message_text(
            msg("language_changed", lang=new_lang)
        )
        return None

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_handlers.py -v`
Expected: all PASS

- [ ] **Step 5: Run all existing tests to ensure no regressions**

Run: `uv run pytest tests/unit/ -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/cps/bot/handlers.py tests/unit/test_handlers.py
git commit -m "feat: add Telegram bot handlers (start, help, monitor, subscribe, language)"
```

---

## Chunk 4: Background Jobs + Notifications

### Task 12: Notification service

**Files:**
- Create: `src/cps/services/notification.py`
- Create: `tests/unit/test_notification.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_notification.py
"""Tests for notification dispatcher."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.services.notification import NotificationSender


class TestNotificationSender:
    @pytest.mark.asyncio
    async def test_send_price_alert(self):
        bot = AsyncMock()
        sender = NotificationSender(bot=bot)
        await sender.send_price_alert(
            telegram_id=123,
            product_name="AirPods Pro",
            current_display="$189",
            target_display="$199",
            lowest_display="$169",
            affiliate_link="https://amazon.com/dp/B0CJ4DKFRG?tag=test-20",
            lang="en",
        )
        bot.send_message.assert_called_once()
        call_kwargs = bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == 123
        assert "AirPods Pro" in call_kwargs["text"]
        assert "$189" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_send_deal_push(self):
        bot = AsyncMock()
        sender = NotificationSender(bot=bot)
        await sender.send_deal_push(
            telegram_id=456,
            product_name="Sony WH-1000XM5",
            category="Electronics",
            current_display="$228",
            previous_display="$349",
            context="Lowest in 4 months",
            affiliate_link="https://amazon.com/dp/B09XS7JWHH?tag=test-20",
            lang="en",
        )
        bot.send_message.assert_called_once()
        call_kwargs = bot.send_message.call_args[1]
        assert call_kwargs["chat_id"] == 456
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_notification.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write minimal implementation**

```python
# src/cps/services/notification.py
"""Notification dispatcher — send alerts via Telegram bot."""
import structlog
from telegram import Bot

from cps.bot.messages import msg

log = structlog.get_logger()


class NotificationSender:
    """Sends notifications to users via Telegram."""

    def __init__(self, *, bot: Bot) -> None:
        self._bot = bot

    async def send_price_alert(
        self,
        *,
        telegram_id: int,
        product_name: str,
        current_display: str,
        target_display: str,
        lowest_display: str,
        affiliate_link: str,
        lang: str = "en",
    ) -> bool:
        """Send a price drop alert. Returns True on success."""
        text = msg(
            "price_alert",
            lang=lang,
            product=product_name,
            current=current_display,
            target=target_display,
            low=lowest_display,
            link=affiliate_link,
        )
        try:
            await self._bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="Markdown",
            )
            log.info("price_alert_sent", telegram_id=telegram_id, product=product_name)
            return True
        except Exception as exc:
            log.error("price_alert_failed", telegram_id=telegram_id, error=str(exc))
            return False

    async def send_deal_push(
        self,
        *,
        telegram_id: int,
        product_name: str,
        category: str,
        current_display: str,
        previous_display: str,
        context: str,
        affiliate_link: str,
        lang: str = "en",
    ) -> bool:
        """Send a deal push notification. Returns True on success."""
        text = msg(
            "deal_push",
            lang=lang,
            category=category,
            product=product_name,
            current=current_display,
            previous=previous_display,
            context=context,
            link=affiliate_link,
        )
        try:
            await self._bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="Markdown",
            )
            log.info("deal_push_sent", telegram_id=telegram_id, category=category)
            return True
        except Exception as exc:
            log.error("deal_push_failed", telegram_id=telegram_id, error=str(exc))
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_notification.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/services/notification.py tests/unit/test_notification.py
git commit -m "feat: add notification sender service"
```

---

### Task 13: Price checker background job

**Files:**
- Create: `src/cps/jobs/__init__.py`
- Create: `src/cps/jobs/price_checker.py`
- Create: `tests/unit/test_price_checker.py`

- [ ] **Step 1: Create package init**

```python
# src/cps/jobs/__init__.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_price_checker.py
"""Tests for price checker background job."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.jobs.price_checker import check_prices


class TestCheckPrices:
    @pytest.mark.asyncio
    async def test_no_active_monitors(self):
        """No monitors → no notifications sent."""
        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock(all=lambda: []))
        sender = AsyncMock()

        result = await check_prices(session=session, sender=sender, affiliate_tag="test-20")
        assert result["checked"] == 0
        assert result["notified"] == 0

    @pytest.mark.asyncio
    async def test_price_below_target_sends_alert(self):
        """When price <= target, sender.send_price_alert should be called."""
        from unittest.mock import patch, PropertyMock

        # Mock the DB query to return one monitor with target 30000
        mock_monitor = MagicMock(
            target_price_cents=30000,
            last_notified_at=None,
            is_active=True,
        )
        mock_user = MagicMock(
            telegram_id=123,
            language="en",
            is_active=True,
        )
        mock_product = MagicMock(
            id=1, asin="B08N5WRWNW", title="Test Product"
        )
        mock_summary = MagicMock(
            current_price=25000,  # Below target of 30000
            lowest_price=20000,
            highest_price=40000,
        )

        session = AsyncMock()
        # First execute: monitors query
        session.execute = AsyncMock(
            side_effect=[
                MagicMock(all=lambda: [(mock_monitor, mock_user, mock_product)]),
                MagicMock(scalar_one_or_none=lambda: mock_summary),
            ]
        )

        sender = AsyncMock()
        sender.send_price_alert = AsyncMock(return_value=True)

        result = await check_prices(session=session, sender=sender, affiliate_tag="test-20")
        assert result["checked"] == 1
        assert result["notified"] == 1
        sender.send_price_alert.assert_called_once()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_price_checker.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 4: Write minimal implementation**

```python
# src/cps/jobs/price_checker.py
"""Background job: check monitored prices against user targets."""
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import (
    NotificationLog,
    PriceMonitor,
    PriceSummary,
    Product,
    TelegramUser,
)
from cps.services.affiliate import build_affiliate_link
from cps.services.notification import NotificationSender
from cps.services.price_analysis import analyze_price

log = structlog.get_logger()

# Don't re-notify for the same monitor within this window
NOTIFICATION_COOLDOWN = timedelta(hours=24)


async def check_prices(
    *,
    session: AsyncSession,
    sender: NotificationSender,
    affiliate_tag: str = "buypulse-20",
) -> dict:
    """Check all active monitors and send alerts where price <= target.

    Returns summary dict with counts.
    """
    now = datetime.now(timezone.utc)
    cooldown_cutoff = now - NOTIFICATION_COOLDOWN

    # Get all active monitors with target prices
    result = await session.execute(
        select(PriceMonitor, TelegramUser, Product)
        .join(TelegramUser, PriceMonitor.user_id == TelegramUser.id)
        .join(Product, PriceMonitor.product_id == Product.id)
        .where(
            PriceMonitor.is_active == True,
            PriceMonitor.target_price_cents.is_not(None),
            TelegramUser.is_active == True,
        )
    )
    rows = result.all()

    checked = 0
    notified = 0

    for monitor, user, product in rows:
        checked += 1

        # Skip if recently notified
        if monitor.last_notified_at and monitor.last_notified_at > cooldown_cutoff:
            continue

        # Get latest price summary
        summary_result = await session.execute(
            select(PriceSummary)
            .where(PriceSummary.product_id == product.id)
            .order_by(PriceSummary.updated_at.desc())
            .limit(1)
        )
        summary = summary_result.scalar_one_or_none()

        if summary is None or summary.current_price is None:
            continue

        current_price = summary.current_price

        # Check if price meets target
        if current_price <= monitor.target_price_cents:
            report = analyze_price(
                current_cents=current_price,
                lowest_cents=summary.lowest_price or current_price,
                highest_cents=summary.highest_price or current_price,
            )

            link = build_affiliate_link(product.asin, tag=affiliate_tag)

            success = await sender.send_price_alert(
                telegram_id=user.telegram_id,
                product_name=product.title or product.asin,
                current_display=report.current_display,
                target_display=f"${monitor.target_price_cents / 100:.2f}",
                lowest_display=report.lowest_display,
                affiliate_link=link,
                lang=user.language,
            )

            if success:
                notified += 1
                monitor.last_notified_at = now

                # Log notification
                notification = NotificationLog(
                    user_id=user.id,
                    product_id=product.id,
                    notification_type="price_alert",
                    affiliate_tag=affiliate_tag,
                )
                session.add(notification)

    await session.flush()
    log.info("price_check_complete", checked=checked, notified=notified)
    return {"checked": checked, "notified": notified}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_price_checker.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/cps/jobs/__init__.py src/cps/jobs/price_checker.py tests/unit/test_price_checker.py
git commit -m "feat: add price checker background job"
```

---

### Task 14: Deal scanner background job

**Files:**
- Create: `src/cps/jobs/deal_scanner.py`
- Create: `tests/unit/test_deal_scanner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_deal_scanner.py
"""Tests for deal scanner background job."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.jobs.deal_scanner import scan_deals, is_near_historical_low


class TestIsNearHistoricalLow:
    def test_at_lowest(self):
        assert is_near_historical_low(current_cents=10000, lowest_cents=10000) is True

    def test_within_tolerance(self):
        # 10500 is 5% above lowest 10000 — within 10% tolerance
        assert is_near_historical_low(current_cents=10500, lowest_cents=10000) is True

    def test_at_tolerance_boundary(self):
        # 11000 is exactly 10% above lowest 10000 — still within
        assert is_near_historical_low(current_cents=11000, lowest_cents=10000) is True

    def test_above_tolerance(self):
        # 11100 is 11% above lowest 10000 — outside tolerance
        assert is_near_historical_low(current_cents=11100, lowest_cents=10000) is False

    def test_much_higher(self):
        assert is_near_historical_low(current_cents=15000, lowest_cents=10000) is False

    def test_custom_tolerance(self):
        assert is_near_historical_low(current_cents=10500, lowest_cents=10000, tolerance=0.03) is False


class TestScanDeals:
    @pytest.mark.asyncio
    async def test_no_subscriptions(self):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock(all=lambda: []))
        sender = AsyncMock()
        result = await scan_deals(session=session, sender=sender, affiliate_tag="test-20")
        assert result["scanned"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_deal_scanner.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Write minimal implementation**

```python
# src/cps/jobs/deal_scanner.py
"""Background job: scan for significant price drops in subscribed categories."""
from datetime import datetime, timezone

import structlog
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import (
    CategorySubscription,
    NotificationLog,
    PriceSummary,
    Product,
    TelegramUser,
)
from cps.services.affiliate import build_affiliate_link
from cps.services.notification import NotificationSender

log = structlog.get_logger()

NEAR_LOW_TOLERANCE = 0.10  # Within 10% of historical low = deal


def is_near_historical_low(
    *,
    current_cents: int,
    lowest_cents: int,
    tolerance: float = NEAR_LOW_TOLERANCE,
) -> bool:
    """Check if current price is near the historical low.

    A 'deal' means the price is within tolerance of the all-time low.
    This avoids false positives from comparing against highest price.
    """
    if lowest_cents <= 0 or current_cents <= 0:
        return False
    return current_cents <= lowest_cents * (1 + tolerance)


async def scan_deals(
    *,
    session: AsyncSession,
    sender: NotificationSender,
    affiliate_tag: str = "buypulse-20",
) -> dict:
    """Scan products in subscribed categories for significant price drops.

    Compares current_price against highest_price from price_summary.
    Returns summary dict with counts.
    """
    # Get all active category subscriptions
    result = await session.execute(
        select(distinct(CategorySubscription.category))
        .where(CategorySubscription.is_active == True)
    )
    active_categories = [row[0] for row in result.all()]

    if not active_categories:
        return {"scanned": 0, "deals_found": 0, "notifications_sent": 0}

    scanned = 0
    deals_found = 0
    notifications_sent = 0

    for category in active_categories:
        # Find products in this category with price summaries
        result = await session.execute(
            select(Product, PriceSummary)
            .join(PriceSummary, PriceSummary.product_id == Product.id)
            .where(Product.category == category)
        )
        products = result.all()

        for product, summary in products:
            scanned += 1

            if summary.current_price is None or summary.lowest_price is None:
                continue

            if not is_near_historical_low(
                current_cents=summary.current_price,
                lowest_cents=summary.lowest_price,
            ):
                continue

            deals_found += 1

            # Find subscribers for this category
            sub_result = await session.execute(
                select(TelegramUser)
                .join(CategorySubscription, CategorySubscription.user_id == TelegramUser.id)
                .where(
                    CategorySubscription.category == category,
                    CategorySubscription.is_active == True,
                    TelegramUser.is_active == True,
                )
            )
            subscribers = sub_result.scalars().all()

            for user in subscribers:
                link = build_affiliate_link(product.asin, tag=affiliate_tag)
                if summary.lowest_price > 0:
                    pct_above_low = round(
                        (summary.current_price - summary.lowest_price) / summary.lowest_price * 100
                    )
                    context = f"Near historical low (only {pct_above_low}% above lowest)"
                else:
                    context = "Near historical low"

                success = await sender.send_deal_push(
                    telegram_id=user.telegram_id,
                    product_name=product.title or product.asin,
                    category=category,
                    current_display=f"${summary.current_price / 100:.2f}",
                    previous_display=f"${summary.lowest_price / 100:.2f}",
                    context=context,
                    affiliate_link=link,
                    lang=user.language,
                )

                if success:
                    notifications_sent += 1
                    notification = NotificationLog(
                        user_id=user.id,
                        product_id=product.id,
                        notification_type="deal_push",
                        affiliate_tag=affiliate_tag,
                    )
                    session.add(notification)

    await session.flush()
    log.info(
        "deal_scan_complete",
        scanned=scanned,
        deals_found=deals_found,
        notifications_sent=notifications_sent,
    )
    return {
        "scanned": scanned,
        "deals_found": deals_found,
        "notifications_sent": notifications_sent,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_deal_scanner.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/jobs/deal_scanner.py tests/unit/test_deal_scanner.py
git commit -m "feat: add deal scanner background job"
```

---

## Chunk 5: Bot Runner + CLI Integration

### Task 15: Register background jobs in bot app

**Files:**
- Modify: `src/cps/bot/app.py`

- [ ] **Step 1: Add job queue registration to create_bot_app**

Add job scheduling to the bot app factory. python-telegram-bot v21+ includes JobQueue via APScheduler.

```python
# Add to create_bot_app() in src/cps/bot/app.py, after handler registration:

async def _run_price_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback: run price checker."""
    from cps.jobs.price_checker import check_prices
    from cps.services.notification import NotificationSender

    factory = context.bot_data["session_factory"]
    tag = context.bot_data.get("affiliate_tag", "buypulse-20")
    sender = NotificationSender(bot=context.bot)

    async with factory() as session:
        result = await check_prices(session=session, sender=sender, affiliate_tag=tag)
        await session.commit()
    log.info("scheduled_price_check", **result)


async def _run_deal_scan(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback: run deal scanner."""
    from cps.jobs.deal_scanner import scan_deals
    from cps.services.notification import NotificationSender

    factory = context.bot_data["session_factory"]
    tag = context.bot_data.get("affiliate_tag", "buypulse-20")
    sender = NotificationSender(bot=context.bot)

    async with factory() as session:
        result = await scan_deals(session=session, sender=sender, affiliate_tag=tag)
        await session.commit()
    log.info("scheduled_deal_scan", **result)
```

Register jobs in `create_bot_app`:

```python
    # Schedule background jobs
    app.job_queue.run_repeating(
        _run_price_check,
        interval=price_check_interval_hours * 3600,
        first=60,  # first run 60s after startup
        name="price_checker",
    )
    app.job_queue.run_repeating(
        _run_deal_scan,
        interval=deal_scan_interval_hours * 3600,
        first=120,
        name="deal_scanner",
    )
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/test_bot_app.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/cps/bot/app.py
git commit -m "feat: register price checker and deal scanner as scheduled jobs"
```

---

### Task 16: CLI bot command

**Files:**
- Modify: `src/cps/cli.py`

- [ ] **Step 1: Add bot command group to CLI**

```python
# Add to src/cps/cli.py:

bot_app_cmd = typer.Typer(help="Telegram bot operations")
app.add_typer(bot_app_cmd, name="bot")


@bot_app_cmd.command("run")
def bot_run() -> None:
    """Start the Telegram bot (polling mode)."""
    settings = get_settings()
    _configure_logging(settings.log_level, settings.log_format)

    if not settings.telegram_bot_token:
        typer.echo("ERROR: TELEGRAM_BOT_TOKEN not set", err=True)
        raise typer.Exit(1)

    from cps.bot.app import create_bot_app

    bot = create_bot_app(
        token=settings.telegram_bot_token,
        db_url=settings.database_url,
        affiliate_tag=settings.affiliate_tag,
        price_check_interval_hours=settings.price_check_interval_hours,
        deal_scan_interval_hours=settings.deal_scan_interval_hours,
    )

    typer.echo("Starting BuyPulse bot (polling mode)...")
    bot.run_polling()
```

- [ ] **Step 2: Test CLI help**

Run: `uv run cps bot --help`
Expected: Shows "bot run" subcommand

- [ ] **Step 3: Commit**

```bash
git add src/cps/cli.py
git commit -m "feat: add 'cps bot run' CLI command"
```

---

### Task 17: Integration tests

**Files:**
- Create: `tests/integration/test_user_repo.py`
- Create: `tests/integration/test_bot_e2e.py`

- [ ] **Step 1: Write user repository integration test**

```python
# tests/integration/test_user_repo.py
"""Integration tests for user-layer DB operations."""
import pytest
from sqlalchemy import select

from cps.db.models import (
    CategorySubscription,
    PriceMonitor,
    Product,
    TelegramUser,
)


@pytest.mark.asyncio
async def test_create_user(db_session):
    user = TelegramUser(telegram_id=123456, username="testuser", first_name="Test")
    db_session.add(user)
    await db_session.flush()
    assert user.id is not None
    assert user.language == "en"
    assert user.monitor_limit == 20


@pytest.mark.asyncio
async def test_create_monitor(db_session):
    # Create user + product first
    user = TelegramUser(telegram_id=111, username="u1")
    db_session.add(user)
    product = Product(asin="B08N5WRWNW", title="Test Product")
    db_session.add(product)
    await db_session.flush()

    monitor = PriceMonitor(
        user_id=user.id,
        product_id=product.id,
        target_price_cents=29900,
    )
    db_session.add(monitor)
    await db_session.flush()
    assert monitor.id is not None
    assert monitor.is_active is True


@pytest.mark.asyncio
async def test_monitor_unique_constraint(db_session):
    """Can't monitor the same product twice."""
    user = TelegramUser(telegram_id=222, username="u2")
    db_session.add(user)
    product = Product(asin="B09V3KXJPB", title="Product 2")
    db_session.add(product)
    await db_session.flush()

    m1 = PriceMonitor(user_id=user.id, product_id=product.id, target_price_cents=10000)
    db_session.add(m1)
    await db_session.flush()

    m2 = PriceMonitor(user_id=user.id, product_id=product.id, target_price_cents=20000)
    db_session.add(m2)
    with pytest.raises(Exception):  # IntegrityError
        await db_session.flush()


@pytest.mark.asyncio
async def test_category_subscription(db_session):
    user = TelegramUser(telegram_id=333, username="u3")
    db_session.add(user)
    await db_session.flush()

    sub = CategorySubscription(user_id=user.id, category="Electronics")
    db_session.add(sub)
    await db_session.flush()
    assert sub.id is not None
```

- [ ] **Step 2: Run integration tests (requires Docker DB)**

Run: `uv run pytest tests/integration/test_user_repo.py -v`
Expected: all PASS (requires Docker containers running)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_user_repo.py
git commit -m "test: add user-layer integration tests"
```

---

### Task 18: Full test suite + coverage check

- [ ] **Step 1: Run all unit tests**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: all PASS

- [ ] **Step 2: Run coverage check**

Run: `uv run pytest tests/unit/ --cov=cps --cov-report=term-missing`
Expected: ≥80% coverage

- [ ] **Step 3: Run integration tests (if Docker is running)**

Run: `uv run pytest tests/integration/ -v --tb=short`
Expected: all PASS

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "test: ensure full test suite passes with 80%+ coverage"
```

---

## Chunk 6: Deployment Config

### Task 19: Environment variables documentation

**Files:**
- Modify: `.env.example` (create if not exists)

- [ ] **Step 1: Create .env.example with all required vars**

```bash
# .env.example — copy to .env and fill in values

# Database
DATABASE_URL=postgresql+asyncpg://cps:cps_password@localhost:5432/cps

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather

# Affiliate
AFFILIATE_TAG=buypulse-20

# Background Jobs
PRICE_CHECK_INTERVAL_HOURS=6
DEAL_SCAN_INTERVAL_HOURS=12

# CCC Crawler
CCC_RATE_LIMIT=1.0

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=console
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add .env.example with all config variables"
```

---

### Task 20: Systemd service file for VPS deployment

**Files:**
- Create: `deploy/buypulse-bot.service`

- [ ] **Step 1: Create systemd unit file**

```ini
# deploy/buypulse-bot.service
[Unit]
Description=BuyPulse Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=cps
WorkingDirectory=/opt/cps
EnvironmentFile=/opt/cps/.env
ExecStart=/opt/cps/.venv/bin/cps bot run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Commit**

```bash
mkdir -p deploy
git add deploy/buypulse-bot.service
git commit -m "chore: add systemd service file for VPS deployment"
```

---

### Task 21: Final integration smoke test

- [ ] **Step 1: Start Docker DB + run migrations**

```bash
docker compose up -d
uv run alembic upgrade head
```

- [ ] **Step 2: Create a test bot token with @BotFather** (manual)

- [ ] **Step 3: Run bot in polling mode**

```bash
TELEGRAM_BOT_TOKEN=your_test_token uv run cps bot run
```

- [ ] **Step 4: Test manually in Telegram**

1. Send `/start` → should get welcome message
2. Send an Amazon link → should get price report (if ASIN in DB)
3. Send `/monitors` → should show monitor list
4. Send `/subscribe` → should show category keyboard
5. Send `/language` → should show language picker

- [ ] **Step 5: Stop bot and commit any final fixes**

```bash
git add -A
git commit -m "test: verify bot smoke test passing"
```
