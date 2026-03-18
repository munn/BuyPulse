# BuyPulse V1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot that lets US consumers check Amazon product prices (via link, ASIN, or natural language), set price alerts with smart target suggestions, and receive AI-driven deal pushes — monetized through affiliate links on every interaction.

**Architecture:** Extend the existing CPS Python codebase (Phase 1: CCC price data pipeline) with four new packages: `bot/` (Telegram interface), `services/` (business logic), `ai/` (Claude Haiku NLP), `jobs/` (background tasks). Reuse the existing async SQLAlchemy 2.0 stack, CCC pipeline, and PostgreSQL database. python-telegram-bot v21+ for Telegram with built-in JobQueue (APScheduler) for periodic tasks.

**Tech Stack:** python-telegram-bot v21+ (with job-queue extra), anthropic SDK, existing SQLAlchemy 2.0 async + asyncpg, PostgreSQL, pytest + pytest-asyncio

**Key References:**
- V1 design spec: `docs/superpowers/specs/2026-03-16-buypulse-v1-design.md`
- Existing DB models: `src/cps/db/models.py`
- Existing config: `src/cps/config.py`
- Existing pipeline: `src/cps/pipeline/orchestrator.py`
- Existing CLI: `src/cps/cli.py`

---

## File Structure

### New Files

```
src/cps/
├── bot/
│   ├── __init__.py              # Package init
│   ├── app.py                   # Application factory + startup/shutdown hooks
│   ├── handlers/
│   │   ├── __init__.py          # register_handlers() — wires all handlers
│   │   ├── start.py             # /start onboarding with demo product
│   │   ├── price_check.py       # Text message handler (URL/ASIN/NLP dispatch)
│   │   ├── monitors.py          # /monitors list + remove
│   │   ├── settings.py          # /settings, /language, /help commands
│   │   └── callbacks.py         # All CallbackQuery handlers (buttons)
│   ├── messages.py              # i18n message templates (EN + ES, 3 density levels)
│   ├── keyboards.py             # InlineKeyboard factories (buy, alert, detail toggle, etc.)
│   └── rate_limiter.py          # Per-user rate limiting (msg/min + queries/day)
├── services/
│   ├── __init__.py              # Package init
│   ├── asin_parser.py           # Input classification (URL → ASIN → NLP) + extraction
│   ├── price_service.py         # Percentile calculation, verdict, target suggestions
│   ├── affiliate.py             # Amazon affiliate link builder (product + search URLs)
│   ├── user_service.py          # User CRUD, language/density prefs, notification state machine
│   ├── monitor_service.py       # Monitor CRUD, 20-limit check, cooldown check
│   ├── search_service.py        # Three-tier waterfall (DB fuzzy → API → fallback link)
│   ├── notification_service.py  # Telegram push with cooldown + blocked detection
│   ├── interaction_service.py   # Record user interactions, behavior pattern queries
│   └── deal_service.py          # Three-layer deal detection (related/global/behavioral)
├── ai/
│   ├── __init__.py              # Package init
│   └── client.py                # Claude Haiku wrapper (search intent + language detection)
├── jobs/
│   ├── __init__.py              # Package init
│   ├── price_checker.py         # Periodic: crawl monitored ASINs → check targets → notify
│   ├── deal_scanner.py          # Periodic: detect deals → push to eligible users
│   ├── crawl_scheduler.py       # On-demand crawl requests + re-crawl scheduling
│   └── engagement.py            # Adaptive frequency: downgrade inactive → re-engage returning
tests/
├── unit/
│   ├── test_user_models.py      # Schema validation for 5 new tables
│   ├── test_asin_parser.py      # URL/ASIN/NLP classification
│   ├── test_price_service.py    # Percentile, verdict, target suggestions
│   ├── test_affiliate.py        # Link generation
│   ├── test_user_service.py     # User CRUD + state transitions
│   ├── test_monitor_service.py  # Monitor CRUD + limits
│   ├── test_search_service.py   # Three-tier waterfall
│   ├── test_ai_client.py        # AI client (mocked API)
│   ├── test_messages.py         # Template rendering (EN + ES, 3 densities)
│   ├── test_keyboards.py        # Keyboard structure
│   ├── test_rate_limiter.py     # Rate limit logic (reuse existing pattern)
│   ├── test_notification_service.py  # Send + cooldown + blocked
│   ├── test_interaction_service.py   # Record + query
│   ├── test_deal_service.py     # Deal detection layers
│   └── test_handlers.py         # Handler dispatch (mocked services)
├── integration/
│   ├── test_user_repo.py        # User + interaction DB operations
│   ├── test_monitor_repo.py     # Monitor + notification DB operations
│   └── test_bot_e2e.py          # End-to-end bot flow with real DB
```

### Modified Files

```
src/cps/db/models.py               # Add 5 new tables + Product relationship additions
src/cps/config.py                  # Add telegram_bot_token, affiliate_tag, anthropic_api_key, demo_asin
src/cps/pipeline/orchestrator.py   # PriceSummary INSERT → UPSERT for re-crawl data freshness
pyproject.toml                     # Add python-telegram-bot[job-queue], anthropic
alembic/versions/002_user_layer.py # Migration for 5 new tables
```

---

## Chunk 1: Foundation (Database + Config + Dependencies)

### Task 1: Add 5 user-layer ORM models

**Files:**
- Modify: `src/cps/db/models.py`
- Create: `tests/unit/test_user_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_user_models.py
"""Unit tests for user-layer ORM models — schema validation only."""
from cps.db.models import (
    DealDismissal,
    NotificationLog,
    PriceMonitor,
    TelegramUser,
    UserInteraction,
)


class TestTelegramUser:
    def test_tablename(self):
        assert TelegramUser.__tablename__ == "telegram_users"

    def test_columns_exist(self):
        cols = {c.name for c in TelegramUser.__table__.columns}
        assert cols >= {
            "id", "telegram_id", "username", "first_name",
            "language", "density_preference", "monitor_limit",
            "notification_state", "last_interaction_at",
            "created_at", "updated_at",
        }

    def test_telegram_id_unique(self):
        col = TelegramUser.__table__.c.telegram_id
        assert col.unique is True

    def test_defaults(self):
        user = TelegramUser(telegram_id=12345)
        assert user.monitor_limit == 20  # Python-side default


class TestPriceMonitor:
    def test_tablename(self):
        assert PriceMonitor.__tablename__ == "price_monitors"

    def test_columns_exist(self):
        cols = {c.name for c in PriceMonitor.__table__.columns}
        assert cols >= {
            "id", "user_id", "product_id", "target_price",
            "is_active", "last_notified_at", "created_at", "updated_at",
        }

    def test_unique_constraint(self):
        constraints = [
            c.name for c in PriceMonitor.__table__.constraints
            if hasattr(c, "columns") and len(c.columns) > 1
        ]
        assert any("user_product" in (name or "") for name in constraints)


class TestNotificationLog:
    def test_tablename(self):
        assert NotificationLog.__tablename__ == "notification_log"

    def test_columns_exist(self):
        cols = {c.name for c in NotificationLog.__table__.columns}
        assert cols >= {
            "id", "user_id", "product_id", "notification_type",
            "message_text", "affiliate_tag", "clicked", "created_at",
        }


class TestUserInteraction:
    def test_tablename(self):
        assert UserInteraction.__tablename__ == "user_interactions"

    def test_columns_exist(self):
        cols = {c.name for c in UserInteraction.__table__.columns}
        assert cols >= {
            "id", "user_id", "interaction_type", "payload", "created_at",
        }


class TestDealDismissal:
    def test_tablename(self):
        assert DealDismissal.__tablename__ == "deal_dismissals"

    def test_columns_exist(self):
        cols = {c.name for c in DealDismissal.__table__.columns}
        assert cols >= {
            "id", "user_id", "dismissed_category", "dismissed_asin", "created_at",
        }

    def test_check_constraint_exists(self):
        check_constraints = [
            c for c in DealDismissal.__table__.constraints
            if type(c).__name__ == "CheckConstraint"
        ]
        assert len(check_constraints) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_user_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'TelegramUser' from 'cps.db.models'`

- [ ] **Step 3: Write the 5 new models**

Add to `src/cps/db/models.py` after the existing `CrawlTask` class (also add `CheckConstraint`, `UniqueConstraint` to the SQLAlchemy imports):

```python
class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(5), nullable=False, server_default="en")
    density_preference: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="standard"
    )
    monitor_limit: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=20)
    notification_state: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active"
    )
    last_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    # Relationships
    monitors: Mapped[list["PriceMonitor"]] = relationship(back_populates="user")
    interactions: Mapped[list["UserInteraction"]] = relationship(back_populates="user")
    dismissals: Mapped[list["DealDismissal"]] = relationship(back_populates="user")
    notifications: Mapped[list["NotificationLog"]] = relationship(back_populates="user")

    __table_args__ = (
        Index("idx_tu_notification_state", "notification_state"),
        Index("idx_tu_last_interaction", "last_interaction_at"),
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
    target_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    # Relationships
    user: Mapped["TelegramUser"] = relationship(back_populates="monitors")
    product: Mapped["Product"] = relationship(back_populates="monitors")

    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_monitors_user_product"),
        Index("idx_pm_user_active", "user_id", "is_active"),
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
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    affiliate_tag: Mapped[str | None] = mapped_column(String(50), nullable=True)
    clicked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user: Mapped["TelegramUser"] = relationship(back_populates="notifications")

    __table_args__ = (
        Index("idx_nl_user_type", "user_id", "notification_type"),
    )


class UserInteraction(Base):
    __tablename__ = "user_interactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("telegram_users.id"), nullable=False
    )
    interaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user: Mapped["TelegramUser"] = relationship(back_populates="interactions")

    __table_args__ = (
        Index("idx_ui_user_type", "user_id", "interaction_type"),
        Index("idx_ui_created", "created_at"),
    )


class DealDismissal(Base):
    __tablename__ = "deal_dismissals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("telegram_users.id"), nullable=False
    )
    dismissed_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dismissed_asin: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user: Mapped["TelegramUser"] = relationship(back_populates="dismissals")

    __table_args__ = (
        CheckConstraint(
            "dismissed_category IS NOT NULL OR dismissed_asin IS NOT NULL",
            name="ck_dismissals_has_target",
        ),
        Index("idx_dd_user", "user_id"),
    )
```

Also add `Product.monitors` relationship after `Product.crawl_task`:

```python
    monitors: Mapped[list["PriceMonitor"]] = relationship(back_populates="product")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_user_models.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/db/models.py tests/unit/test_user_models.py
git commit -m "feat: add 5 user-layer ORM models (telegram_users, price_monitors, notification_log, user_interactions, deal_dismissals)"
```

---

### Task 2: Alembic migration for user-layer tables

**Files:**
- Create: `alembic/versions/002_user_layer.py`

- [ ] **Step 1: Create the migration file**

```python
# alembic/versions/002_user_layer.py
"""Add user-layer tables for Telegram bot.

Revision ID: 002
Revises: 001
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"


def upgrade() -> None:
    # telegram_users
    op.create_table(
        "telegram_users",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("language", sa.String(5), nullable=False, server_default="en"),
        sa.Column("density_preference", sa.String(20), nullable=False, server_default="standard"),
        sa.Column("monitor_limit", sa.SmallInteger, nullable=False, server_default="20"),
        sa.Column("notification_state", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_tu_notification_state", "telegram_users", ["notification_state"])
    op.create_index("idx_tu_last_interaction", "telegram_users", ["last_interaction_at"])

    # price_monitors
    op.create_table(
        "price_monitors",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("telegram_users.id"), nullable=False),
        sa.Column("product_id", sa.BigInteger, sa.ForeignKey("products.id"), nullable=False),
        sa.Column("target_price", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "product_id", name="uq_monitors_user_product"),
    )
    op.create_index("idx_pm_user_active", "price_monitors", ["user_id", "is_active"])

    # notification_log
    op.create_table(
        "notification_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("telegram_users.id"), nullable=False),
        sa.Column("product_id", sa.BigInteger, sa.ForeignKey("products.id"), nullable=True),
        sa.Column("notification_type", sa.String(20), nullable=False),
        sa.Column("message_text", sa.Text, nullable=False),
        sa.Column("affiliate_tag", sa.String(50), nullable=True),
        sa.Column("clicked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_nl_user_type", "notification_log", ["user_id", "notification_type"])

    # user_interactions
    op.create_table(
        "user_interactions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("telegram_users.id"), nullable=False),
        sa.Column("interaction_type", sa.String(20), nullable=False),
        sa.Column("payload", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_ui_user_type", "user_interactions", ["user_id", "interaction_type"])
    op.create_index("idx_ui_created", "user_interactions", ["created_at"])

    # deal_dismissals
    op.create_table(
        "deal_dismissals",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("telegram_users.id"), nullable=False),
        sa.Column("dismissed_category", sa.String(255), nullable=True),
        sa.Column("dismissed_asin", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "dismissed_category IS NOT NULL OR dismissed_asin IS NOT NULL",
            name="ck_dismissals_has_target",
        ),
    )
    op.create_index("idx_dd_user", "deal_dismissals", ["user_id"])


def downgrade() -> None:
    op.drop_table("deal_dismissals")
    op.drop_table("user_interactions")
    op.drop_table("notification_log")
    op.drop_table("price_monitors")
    op.drop_table("telegram_users")
```

- [ ] **Step 2: Run migration locally**

Run: `uv run alembic upgrade head`
Expected: Upgrade from 001 → 002 succeeds

- [ ] **Step 3: Verify tables exist**

Run: `uv run python -c "from cps.db.models import TelegramUser, PriceMonitor; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/002_user_layer.py
git commit -m "feat: add Alembic migration 002 for user-layer tables"
```

---

### Task 3: Extend config with bot settings

**Files:**
- Modify: `src/cps/config.py`
- Modify: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to existing `tests/unit/test_config.py`:

```python
def test_bot_settings_fields():
    """Verify new bot-related fields exist on Settings."""
    from cps.config import Settings
    field_names = set(Settings.model_fields.keys())
    assert field_names >= {
        "telegram_bot_token", "affiliate_tag",
        "anthropic_api_key", "demo_asin",
    }

def test_bot_defaults():
    """Verify sensible defaults for bot settings."""
    from cps.config import Settings
    fields = Settings.model_fields
    assert fields["affiliate_tag"].default == ""
    assert fields["demo_asin"].default == "B0D1XD1ZV3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py::test_bot_settings_fields -v`
Expected: FAIL — `AssertionError` (fields don't exist yet)

- [ ] **Step 3: Add bot settings to config**

Add to `src/cps/config.py` in the `Settings` class, after the logging section:

```python
    # Telegram Bot
    telegram_bot_token: str = Field(
        default="",
        description="Telegram Bot API token from @BotFather",
    )
    affiliate_tag: str = Field(
        default="",
        description="Amazon Associates affiliate tag (e.g., buypulse-20)",
    )
    demo_asin: str = Field(
        default="B0D1XD1ZV3",
        description="ASIN for onboarding demo product (pre-seeded in DB)",
    )

    # AI (Claude)
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for Claude Haiku (NLP + language detection)",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/config.py tests/unit/test_config.py
git commit -m "feat: add telegram bot, affiliate, and AI config settings"
```

---

### Task 4: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add new dependencies**

Add to `dependencies` in `pyproject.toml`:

```toml
    "python-telegram-bot[job-queue]>=21.0",
    "anthropic>=0.40.0",
```

- [ ] **Step 2: Install and verify**

Run: `uv sync`
Expected: All dependencies install successfully

- [ ] **Step 3: Verify imports work**

Run: `uv run python -c "import telegram; import anthropic; print(f'telegram={telegram.__version__}, anthropic={anthropic.__version__}')"`
Expected: Prints version numbers

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add python-telegram-bot and anthropic dependencies"
```

---

## Chunk 2: Core Services (Pure Business Logic)

### Task 5: ASIN parser service

**Files:**
- Create: `src/cps/services/__init__.py`
- Create: `src/cps/services/asin_parser.py`
- Create: `tests/unit/test_asin_parser.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_asin_parser.py
"""Tests for input classification: URL → ASIN → natural language."""
from cps.services.asin_parser import InputType, ParseResult, parse_input


class TestUrlParsing:
    def test_standard_dp_url(self):
        result = parse_input("https://www.amazon.com/dp/B08N5WRWNW")
        assert result == ParseResult(InputType.URL, asin="B08N5WRWNW")

    def test_gp_product_url(self):
        result = parse_input("https://amazon.com/gp/product/B09V3KXJPB?tag=foo")
        assert result == ParseResult(InputType.URL, asin="B09V3KXJPB")

    def test_url_with_surrounding_text(self):
        result = parse_input("check this https://amazon.com/dp/B08N5WRWNW please")
        assert result == ParseResult(InputType.URL, asin="B08N5WRWNW")

    def test_short_url_with_dp(self):
        result = parse_input("https://www.amazon.com/Some-Product-Name/dp/B0BSHF7WHW/ref=sr_1_1")
        assert result == ParseResult(InputType.URL, asin="B0BSHF7WHW")


class TestAsinParsing:
    def test_plain_asin(self):
        result = parse_input("B08N5WRWNW")
        assert result == ParseResult(InputType.ASIN, asin="B08N5WRWNW")

    def test_asin_with_text(self):
        # Per spec: ASIN regex matches first, ignore rest of text
        result = parse_input("B08N5WRWNW is it a good price?")
        assert result == ParseResult(InputType.ASIN, asin="B08N5WRWNW")

    def test_non_b_prefix_not_matched(self):
        # Only B-prefix ASINs matched as standalone
        result = parse_input("A08N5WRWNW")
        assert result.input_type == InputType.NATURAL_LANGUAGE


class TestNaturalLanguage:
    def test_simple_query(self):
        result = parse_input("How much are AirPods Pro?")
        assert result == ParseResult(InputType.NATURAL_LANGUAGE, query="How much are AirPods Pro?")

    def test_empty_after_strip(self):
        result = parse_input("   ")
        assert result == ParseResult(InputType.NATURAL_LANGUAGE, query="")

    def test_url_takes_priority_over_asin(self):
        # URL in text that also contains a standalone ASIN pattern
        result = parse_input("https://amazon.com/dp/B08N5WRWNW B09V3KXJPB")
        assert result.input_type == InputType.URL
        assert result.asin == "B08N5WRWNW"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_asin_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cps.services'`

- [ ] **Step 3: Create the package and implement**

Create `src/cps/services/__init__.py` (empty).

```python
# src/cps/services/asin_parser.py
"""Classify user input as Amazon URL, ASIN, or natural language query.

Detection order (per spec Section 2.2):
1. URL regex — contains amazon.com/dp/ or amazon.com/gp/product/
2. ASIN regex — standalone B[A-Z0-9]{9}
3. Everything else — natural language
"""
import re
from dataclasses import dataclass
from enum import Enum


class InputType(Enum):
    URL = "url"
    ASIN = "asin"
    NATURAL_LANGUAGE = "natural_language"


@dataclass(frozen=True)
class ParseResult:
    input_type: InputType
    asin: str | None = None
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
        return ParseResult(InputType.URL, asin=url_match.group(1).upper())

    # 2. ASIN regex
    asin_match = _ASIN_PATTERN.search(text)
    if asin_match:
        return ParseResult(InputType.ASIN, asin=asin_match.group(0))

    # 3. Natural language
    return ParseResult(InputType.NATURAL_LANGUAGE, query=text.strip())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_asin_parser.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/services/__init__.py src/cps/services/asin_parser.py tests/unit/test_asin_parser.py
git commit -m "feat: add ASIN parser service with URL/ASIN/NLP classification"
```

---

### Task 6: Price analysis service

**Files:**
- Create: `src/cps/services/price_service.py`
- Create: `tests/unit/test_price_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_price_service.py
"""Tests for price percentile, verdict, and target suggestion logic."""
from datetime import date

from cps.services.price_service import (
    Density,
    PriceAnalysis,
    PriceVerdict,
    analyze_price,
    calculate_percentile,
    suggest_targets,
)


class TestPercentile:
    def test_at_historical_low(self):
        assert calculate_percentile(100, [100, 200, 300, 400, 500]) == 0

    def test_at_historical_high(self):
        assert calculate_percentile(500, [100, 200, 300, 400, 500]) == 100

    def test_midpoint(self):
        pct = calculate_percentile(300, [100, 200, 300, 400, 500])
        assert 40 <= pct <= 60  # around 50th percentile

    def test_below_all(self):
        assert calculate_percentile(50, [100, 200, 300]) == 0

    def test_single_price(self):
        assert calculate_percentile(100, [100]) == 0

    def test_empty_history(self):
        assert calculate_percentile(100, []) == 0


class TestAnalyzePrice:
    def test_good_price_verdict(self):
        history = [(date(2025, m, 1), p) for m, p in [
            (1, 24900), (2, 22900), (3, 19900), (4, 16900),
            (5, 18900), (6, 21900), (7, 24900), (8, 22900),
            (9, 19900), (10, 18900), (11, 16900), (12, 18900),
        ]]
        analysis = analyze_price(
            current_price=18900,
            price_history=history,
            lowest_price=16900,
            lowest_date=date(2025, 4, 1),
            highest_price=24900,
            highest_date=date(2025, 1, 1),
        )
        assert analysis.current_price == 18900
        assert analysis.historical_low == 16900
        assert analysis.historical_high == 24900
        assert analysis.percentile <= 30
        assert analysis.verdict in (PriceVerdict.GOOD, PriceVerdict.GREAT)


class TestSuggestTargets:
    def test_returns_historical_low_and_percentile(self):
        analysis = PriceAnalysis(
            current_price=18900,
            historical_low=16900,
            historical_high=24900,
            historical_low_date=date(2025, 4, 1),
            historical_high_date=date(2025, 1, 1),
            percentile=25,
            trend_30d="dropping",
            verdict=PriceVerdict.GOOD,
        )
        targets = suggest_targets(analysis, all_prices=[16900, 18900, 19900, 22900, 24900])
        labels = [t["label"] for t in targets]
        # Should have historical low and 30th percentile options
        assert any("$169" in l for l in labels)
        assert len(targets) >= 2

    def test_no_suggestions_when_at_low(self):
        analysis = PriceAnalysis(
            current_price=16900,
            historical_low=16900,
            historical_high=24900,
            historical_low_date=date(2025, 4, 1),
            historical_high_date=date(2025, 1, 1),
            percentile=0,
            trend_30d="stable",
            verdict=PriceVerdict.GREAT,
        )
        targets = suggest_targets(analysis, all_prices=[16900, 18900, 24900])
        # Historical low equals current — may only have 30th pct or fewer
        assert all(t["price"] <= 16900 for t in targets)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_price_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement price service**

```python
# src/cps/services/price_service.py
"""Price analysis: percentile, verdict, trend, and target suggestions.

All prices in cents. Percentile uses full historical data (not windowed).
"""
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class PriceVerdict(str, Enum):
    GREAT = "great"        # <15th percentile
    GOOD = "good"          # 15-30th
    FAIR = "fair"          # 30-60th
    HIGH = "high"          # 60-85th
    VERY_HIGH = "very_high"  # >85th


class Density(str, Enum):
    COMPACT = "compact"
    STANDARD = "standard"
    DETAILED = "detailed"


@dataclass(frozen=True)
class PriceAnalysis:
    current_price: int
    historical_low: int
    historical_high: int
    historical_low_date: date | None
    historical_high_date: date | None
    percentile: int  # 0-100
    trend_30d: str   # "dropping", "rising", "stable"
    verdict: PriceVerdict


def calculate_percentile(current: int, history: list[int]) -> int:
    """What percentage of historical prices are below `current`."""
    if not history:
        return 0
    below = sum(1 for p in history if p < current)
    return round(below / len(history) * 100)


def _compute_trend(history: list[tuple[date, int]]) -> str:
    """Simple 30-day trend from most recent data points."""
    if len(history) < 2:
        return "stable"
    cutoff = history[-1][0] - timedelta(days=30)
    recent = [p for d, p in history if d >= cutoff]
    if len(recent) < 2:
        return "stable"
    first_half = sum(recent[: len(recent) // 2]) / max(len(recent) // 2, 1)
    second_half = sum(recent[len(recent) // 2 :]) / max(len(recent) - len(recent) // 2, 1)
    ratio = second_half / first_half if first_half else 1.0
    if ratio < 0.95:
        return "dropping"
    if ratio > 1.05:
        return "rising"
    return "stable"


def _verdict_from_percentile(pct: int) -> PriceVerdict:
    if pct < 15:
        return PriceVerdict.GREAT
    if pct < 30:
        return PriceVerdict.GOOD
    if pct < 60:
        return PriceVerdict.FAIR
    if pct < 85:
        return PriceVerdict.HIGH
    return PriceVerdict.VERY_HIGH


def analyze_price(
    current_price: int,
    price_history: list[tuple[date, int]],
    lowest_price: int,
    lowest_date: date | None,
    highest_price: int,
    highest_date: date | None,
) -> PriceAnalysis:
    """Build full price analysis from current price + historical data."""
    all_prices = [p for _, p in price_history]
    pct = calculate_percentile(current_price, all_prices)
    trend = _compute_trend(price_history)
    return PriceAnalysis(
        current_price=current_price,
        historical_low=lowest_price,
        historical_high=highest_price,
        historical_low_date=lowest_date,
        historical_high_date=highest_date,
        percentile=pct,
        trend_30d=trend,
        verdict=_verdict_from_percentile(pct),
    )


def suggest_targets(
    analysis: PriceAnalysis, all_prices: list[int]
) -> list[dict]:
    """Generate smart target price suggestions (spec Section 3.1).

    Returns list of {"label": str, "price": int} dicts.
    Only includes targets that are below or equal to current price.
    """
    targets: list[dict] = []

    # Historical low
    if analysis.historical_low <= analysis.current_price:
        dollars = analysis.historical_low / 100
        targets.append({
            "label": f"Historical low: ${dollars:,.0f}",
            "price": analysis.historical_low,
        })

    # 30th percentile
    if all_prices:
        sorted_prices = sorted(all_prices)
        idx = max(0, int(len(sorted_prices) * 0.30) - 1)
        p30 = sorted_prices[idx]
        if p30 <= analysis.current_price and p30 != analysis.historical_low:
            dollars = p30 / 100
            targets.append({
                "label": f"30th pct: ${dollars:,.0f}",
                "price": p30,
            })

    return targets


def format_price(cents: int) -> str:
    """Format cents as dollar string: 18900 → '$189'."""
    dollars = cents / 100
    if dollars == int(dollars):
        return f"${int(dollars)}"
    return f"${dollars:,.2f}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_price_service.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/services/price_service.py tests/unit/test_price_service.py
git commit -m "feat: add price analysis service with percentile, verdict, and target suggestions"
```

---

### Task 7: Affiliate link service

**Files:**
- Create: `src/cps/services/affiliate.py`
- Create: `tests/unit/test_affiliate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_affiliate.py
"""Tests for affiliate link generation."""
from cps.services.affiliate import build_product_link, build_search_link


def test_product_link():
    url = build_product_link("B08N5WRWNW", "buypulse-20")
    assert url == "https://www.amazon.com/dp/B08N5WRWNW?tag=buypulse-20"


def test_search_link():
    url = build_search_link("airpods pro", "buypulse-20")
    assert "amazon.com/s?" in url
    assert "tag=buypulse-20" in url
    assert "airpods" in url.lower()


def test_search_link_encodes_spaces():
    url = build_search_link("robot vacuum cleaner", "tag1")
    assert " " not in url.split("?")[1]  # query params should be encoded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_affiliate.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# src/cps/services/affiliate.py
"""Amazon affiliate link builder — every user-facing URL carries the tag."""
from urllib.parse import quote_plus


def build_product_link(asin: str, tag: str) -> str:
    """Build tagged product URL: https://www.amazon.com/dp/{ASIN}?tag={tag}."""
    return f"https://www.amazon.com/dp/{asin}?tag={tag}"


def build_search_link(query: str, tag: str) -> str:
    """Build tagged search URL for fallback tier."""
    return f"https://www.amazon.com/s?k={quote_plus(query)}&tag={tag}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_affiliate.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/services/affiliate.py tests/unit/test_affiliate.py
git commit -m "feat: add affiliate link service for product and search URLs"
```

---

### Task 8: User service (CRUD + notification state machine)

**Files:**
- Create: `src/cps/services/user_service.py`
- Create: `tests/unit/test_user_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_user_service.py
"""Tests for user service — CRUD, language, density, state transitions.

Uses a mock AsyncSession to avoid DB dependency.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.services.user_service import NotificationState, UserService


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return UserService(mock_session)


class TestNotificationState:
    def test_all_states_defined(self):
        states = {s.value for s in NotificationState}
        assert states == {
            "active", "degraded_weekly", "degraded_monthly",
            "stopped", "paused_by_user", "blocked",
        }

    def test_is_pushable(self):
        assert NotificationState.ACTIVE.is_pushable is True
        assert NotificationState.DEGRADED_WEEKLY.is_pushable is True
        assert NotificationState.STOPPED.is_pushable is False
        assert NotificationState.BLOCKED.is_pushable is False


class TestGetOrCreate:
    async def test_creates_new_user(self, service, mock_session):
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        user = await service.get_or_create(telegram_id=12345, username="test")
        mock_session.add.assert_called_once()

    async def test_returns_existing_user(self, service, mock_session):
        existing = MagicMock(telegram_id=12345)
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
        )
        user = await service.get_or_create(telegram_id=12345)
        assert user is existing
        mock_session.add.assert_not_called()


class TestStateTransitions:
    def test_valid_downgrade_path(self):
        assert NotificationState.ACTIVE.can_transition_to(NotificationState.DEGRADED_WEEKLY)
        assert NotificationState.DEGRADED_WEEKLY.can_transition_to(NotificationState.DEGRADED_MONTHLY)
        assert NotificationState.DEGRADED_MONTHLY.can_transition_to(NotificationState.STOPPED)

    def test_reactivation_path(self):
        for state in NotificationState:
            if state != NotificationState.BLOCKED:
                assert state.can_transition_to(NotificationState.ACTIVE) is True

    def test_blocked_is_terminal(self):
        assert NotificationState.BLOCKED.can_transition_to(NotificationState.ACTIVE) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_user_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement user service**

```python
# src/cps/services/user_service.py
"""User CRUD, preferences, and notification state machine.

Notification states (spec Section 8):
  active → degraded_weekly → degraded_monthly → stopped
  any (except blocked) → active (re-engagement)
  any → blocked (Telegram Forbidden)
  active ↔ paused_by_user
"""
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import TelegramUser


class NotificationState(str, Enum):
    ACTIVE = "active"
    DEGRADED_WEEKLY = "degraded_weekly"
    DEGRADED_MONTHLY = "degraded_monthly"
    STOPPED = "stopped"
    PAUSED_BY_USER = "paused_by_user"
    BLOCKED = "blocked"

    @property
    def is_pushable(self) -> bool:
        """Can we send deal pushes in this state?"""
        return self in (
            NotificationState.ACTIVE,
            NotificationState.DEGRADED_WEEKLY,
            NotificationState.DEGRADED_MONTHLY,
        )

    def can_transition_to(self, target: "NotificationState") -> bool:
        """Validate state transition."""
        if self == NotificationState.BLOCKED:
            return False  # terminal state
        if target == NotificationState.BLOCKED:
            return True  # any → blocked
        if target == NotificationState.ACTIVE:
            return self != NotificationState.BLOCKED
        return (self, target) in _VALID_TRANSITIONS


_VALID_TRANSITIONS = {
    (NotificationState.ACTIVE, NotificationState.DEGRADED_WEEKLY),
    (NotificationState.ACTIVE, NotificationState.PAUSED_BY_USER),
    (NotificationState.DEGRADED_WEEKLY, NotificationState.DEGRADED_MONTHLY),
    (NotificationState.DEGRADED_MONTHLY, NotificationState.STOPPED),
    (NotificationState.PAUSED_BY_USER, NotificationState.ACTIVE),
}


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> TelegramUser:
        """Find user by telegram_id or create new one."""
        result = await self._session.execute(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is not None:
            return user

        user = TelegramUser(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_telegram_id(self, telegram_id: int) -> TelegramUser | None:
        result = await self._session.execute(
            select(TelegramUser).where(TelegramUser.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def update_language(self, user: TelegramUser, language: str) -> None:
        user.language = language
        await self._session.flush()

    async def update_density(self, user: TelegramUser, density: str) -> None:
        user.density_preference = density
        await self._session.flush()

    async def record_interaction(self, user: TelegramUser) -> None:
        """Update last_interaction_at timestamp."""
        user.last_interaction_at = datetime.now(timezone.utc)
        await self._session.flush()

    async def mark_blocked(self, user: TelegramUser) -> None:
        """Mark user as blocked (Telegram Forbidden)."""
        user.notification_state = NotificationState.BLOCKED.value
        await self._session.flush()

    async def transition_state(
        self, user: TelegramUser, new_state: NotificationState
    ) -> bool:
        """Transition notification state. Returns False if invalid."""
        current = NotificationState(user.notification_state)
        if not current.can_transition_to(new_state):
            return False
        user.notification_state = new_state.value
        await self._session.flush()
        return True

    def needs_reengagement(self, user: TelegramUser) -> bool:
        """Check if user returning from degraded/stopped state needs re-engagement prompt."""
        return user.notification_state in (
            NotificationState.DEGRADED_WEEKLY.value,
            NotificationState.DEGRADED_MONTHLY.value,
            NotificationState.STOPPED.value,
            NotificationState.PAUSED_BY_USER.value,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_user_service.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/services/user_service.py tests/unit/test_user_service.py
git commit -m "feat: add user service with CRUD and notification state machine"
```

---

### Task 9: Monitor service (CRUD + limits + target suggestions)

**Files:**
- Create: `src/cps/services/monitor_service.py`
- Create: `tests/unit/test_monitor_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_monitor_service.py
"""Tests for monitor service — CRUD, 20-limit, cooldown, target suggestions."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.services.monitor_service import MonitorService


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    return MonitorService(mock_session)


class TestCreateMonitor:
    async def test_rejects_when_at_limit(self, service, mock_session):
        # Simulate 20 existing monitors
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 20
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await service.create_monitor(user_id=1, product_id=99, monitor_limit=20)
        assert result is None  # rejected

    async def test_creates_when_under_limit(self, service, mock_session):
        # First call: count = 5, second call: check existing = None
        count_result = MagicMock(scalar_one=MagicMock(return_value=5))
        existing_result = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        mock_session.execute = AsyncMock(side_effect=[count_result, existing_result])

        result = await service.create_monitor(user_id=1, product_id=99, monitor_limit=20)
        mock_session.add.assert_called_once()


class TestCooldownCheck:
    def test_cooldown_not_expired(self):
        last_notified = datetime.now(timezone.utc) - timedelta(hours=12)
        assert MonitorService.is_cooldown_active(last_notified) is True

    def test_cooldown_expired(self):
        last_notified = datetime.now(timezone.utc) - timedelta(hours=25)
        assert MonitorService.is_cooldown_active(last_notified) is False

    def test_never_notified(self):
        assert MonitorService.is_cooldown_active(None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_monitor_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement monitor service**

```python
# src/cps/services/monitor_service.py
"""Monitor CRUD with 20-limit enforcement and 24h notification cooldown.

Per spec Section 3.2:
- 20 free monitors per user
- 24h notification cooldown per (user, product) pair
- last_notified_at is the cooldown clock
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import PriceMonitor

_COOLDOWN_HOURS = 24


class MonitorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_monitor(
        self,
        user_id: int,
        product_id: int,
        monitor_limit: int = 20,
        target_price: int | None = None,
    ) -> PriceMonitor | None:
        """Create a new monitor. Returns None if at limit or already exists."""
        # Check count
        count_result = await self._session.execute(
            select(func.count()).select_from(PriceMonitor).where(
                PriceMonitor.user_id == user_id,
                PriceMonitor.is_active == True,  # noqa: E712
            )
        )
        if count_result.scalar_one() >= monitor_limit:
            return None

        # Check if already monitoring this product
        existing_result = await self._session.execute(
            select(PriceMonitor).where(
                PriceMonitor.user_id == user_id,
                PriceMonitor.product_id == product_id,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            # Re-activate if was deactivated
            if not existing.is_active:
                existing.is_active = True
                existing.target_price = target_price
                await self._session.flush()
            return existing

        monitor = PriceMonitor(
            user_id=user_id,
            product_id=product_id,
            target_price=target_price,
        )
        self._session.add(monitor)
        await self._session.flush()
        return monitor

    async def remove_monitor(self, user_id: int, product_id: int) -> bool:
        """Deactivate a monitor. Returns False if not found."""
        result = await self._session.execute(
            select(PriceMonitor).where(
                PriceMonitor.user_id == user_id,
                PriceMonitor.product_id == product_id,
            )
        )
        monitor = result.scalar_one_or_none()
        if monitor is None:
            return False
        monitor.is_active = False
        await self._session.flush()
        return True

    async def list_active(self, user_id: int) -> list[PriceMonitor]:
        result = await self._session.execute(
            select(PriceMonitor).where(
                PriceMonitor.user_id == user_id,
                PriceMonitor.is_active == True,  # noqa: E712
            ).order_by(PriceMonitor.created_at)
        )
        return list(result.scalars().all())

    async def count_active(self, user_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(PriceMonitor).where(
                PriceMonitor.user_id == user_id,
                PriceMonitor.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def get_monitors_for_product(self, product_id: int) -> list[PriceMonitor]:
        """All active monitors for a product (for price alert dispatch)."""
        result = await self._session.execute(
            select(PriceMonitor).where(
                PriceMonitor.product_id == product_id,
                PriceMonitor.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def is_cooldown_active(last_notified_at: datetime | None) -> bool:
        """Check if 24h notification cooldown is still active."""
        if last_notified_at is None:
            return False
        return datetime.now(timezone.utc) - last_notified_at < timedelta(hours=_COOLDOWN_HOURS)

    async def mark_notified(self, monitor: PriceMonitor) -> None:
        """Update last_notified_at after sending a price alert."""
        monitor.last_notified_at = datetime.now(timezone.utc)
        await self._session.flush()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_monitor_service.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/services/monitor_service.py tests/unit/test_monitor_service.py
git commit -m "feat: add monitor service with CRUD, 20-limit, and 24h cooldown"
```

---

## Chunk 3: AI Integration + Search + Pipeline Fix

### Task 10: AI client (Claude Haiku for search intent + language detection)

**Files:**
- Create: `src/cps/ai/__init__.py`
- Create: `src/cps/ai/client.py`
- Create: `tests/unit/test_ai_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ai_client.py
"""Tests for AI client — mocked Anthropic API calls."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.ai.client import AIClient


@pytest.fixture
def client():
    return AIClient(api_key="test-key")


class TestExtractSearchIntent:
    async def test_extracts_product_query(self, client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="AirPods Pro")]
        with patch.object(
            client._client.messages, "create", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await client.extract_search_intent("How much are AirPods Pro right now?")
            assert result == "AirPods Pro"

    async def test_uses_haiku_model(self, client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="test")]
        with patch.object(
            client._client.messages, "create", new_callable=AsyncMock, return_value=mock_response
        ) as mock_create:
            await client.extract_search_intent("test query")
            call_kwargs = mock_create.call_args.kwargs
            assert "haiku" in call_kwargs["model"]


class TestDetectLanguage:
    async def test_detects_english(self, client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="en")]
        with patch.object(
            client._client.messages, "create", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await client.detect_language("What's the price of this?")
            assert result == "en"

    async def test_detects_spanish(self, client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="es")]
        with patch.object(
            client._client.messages, "create", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await client.detect_language("Cuanto cuesta esto?")
            assert result == "es"

    async def test_falls_back_to_en(self, client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="fr")]  # unsupported
        with patch.object(
            client._client.messages, "create", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await client.detect_language("Bonjour")
            assert result == "en"  # fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_ai_client.py -v`
Expected: FAIL

- [ ] **Step 3: Implement AI client**

Create `src/cps/ai/__init__.py` (empty).

```python
# src/cps/ai/client.py
"""Claude Haiku wrapper for NLP tasks: search intent extraction + language detection.

Uses Haiku for ~90% of calls (cost-efficient). See spec Section 9.
"""
import anthropic

_HAIKU_MODEL = "claude-haiku-4-5-latest"
_SUPPORTED_LANGUAGES = {"en", "es"}


class AIClient:
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def extract_search_intent(self, text: str) -> str:
        """Extract product search query from natural language.

        Input: "How much are AirPods Pro right now?"
        Output: "AirPods Pro"
        """
        response = await self._client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=100,
            system=(
                "Extract the product name or search query from the user's message. "
                "Return ONLY the product name/query, nothing else. "
                "If the message is not about a product, return the message as-is."
            ),
            messages=[{"role": "user", "content": text}],
        )
        return response.content[0].text.strip()

    async def detect_language(self, text: str) -> str:
        """Detect language of user's message. Returns 'en' or 'es'.

        Falls back to 'en' for unsupported languages.
        """
        response = await self._client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=5,
            system=(
                "Detect the language of the user's message. "
                "Return ONLY the ISO 639-1 code (e.g., 'en', 'es'). Nothing else."
            ),
            messages=[{"role": "user", "content": text}],
        )
        lang = response.content[0].text.strip().lower()[:2]
        return lang if lang in _SUPPORTED_LANGUAGES else "en"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_ai_client.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/ai/__init__.py src/cps/ai/client.py tests/unit/test_ai_client.py
git commit -m "feat: add AI client with Haiku for search intent and language detection"
```

---

### Task 11: Three-tier search service

**Files:**
- Create: `src/cps/services/search_service.py`
- Create: `tests/unit/test_search_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_search_service.py
"""Tests for three-tier search waterfall: DB → API → fallback link."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.services.search_service import SearchResult, SearchService


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    return SearchService(mock_session, affiliate_tag="buypulse-20")


class TestTier1DbSearch:
    async def test_finds_product_by_title(self, service, mock_session):
        product = MagicMock(id=1, asin="B08N5WRWNW", title="AirPods Pro 2")
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = product
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await service.search("airpods pro")
        assert result.product is product
        assert result.source == "db"

    async def test_falls_through_when_no_match(self, service, mock_session):
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await service.search("some obscure product xyz")
        assert result.product is None
        assert result.source == "fallback"
        assert "amazon.com/s?" in result.fallback_url
        assert "buypulse-20" in result.fallback_url


class TestTier3Fallback:
    async def test_fallback_url_contains_query(self, service, mock_session):
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await service.search("robot vacuum")
        assert "robot" in result.fallback_url.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_search_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement search service**

```python
# src/cps/services/search_service.py
"""Three-tier search waterfall (spec Section 2.3).

Tier 1: DB fuzzy match on products.title — zero cost, instant
Tier 2: Amazon Creators API — skipped in V1 (cold-start, not yet available)
Tier 3: Fallback Amazon search link with affiliate tag
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import Product
from cps.services.affiliate import build_search_link


@dataclass(frozen=True)
class SearchResult:
    product: object | None = None  # Product ORM object or None
    source: str = ""               # "db", "api", "fallback"
    fallback_url: str | None = None


class SearchService:
    def __init__(self, session: AsyncSession, affiliate_tag: str) -> None:
        self._session = session
        self._affiliate_tag = affiliate_tag

    async def search(self, query: str) -> SearchResult:
        """Execute three-tier search waterfall."""
        # Tier 1: DB fuzzy match
        product = await self._search_db(query)
        if product is not None:
            return SearchResult(product=product, source="db")

        # Tier 2: Amazon API (V1: skip — cold-start period)
        # TODO: Implement when Creators API access is available

        # Tier 3: Fallback search link
        return SearchResult(
            source="fallback",
            fallback_url=build_search_link(query, self._affiliate_tag),
        )

    async def _search_db(self, query: str) -> object | None:
        """Case-insensitive ILIKE search on products.title."""
        pattern = f"%{query}%"
        result = await self._session.execute(
            select(Product)
            .where(Product.title.ilike(pattern))
            .limit(1)
        )
        return result.scalars().first()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_search_service.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/services/search_service.py tests/unit/test_search_service.py
git commit -m "feat: add three-tier search service (DB fuzzy → API placeholder → fallback)"
```

---

### Task 12: PriceSummary UPSERT + CrawlTask on-demand upsert

**Files:**
- Modify: `src/cps/pipeline/orchestrator.py`
- Create: `tests/unit/test_orchestrator_upsert.py`

This task fixes two things per spec:
1. `PriceSummary` INSERT → UPSERT so re-crawled ASINs get fresh `current_price`
2. Add a helper for `CrawlTask` upsert (on-demand crawl: if exists → update priority/status)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_orchestrator_upsert.py
"""Tests for PriceSummary upsert and CrawlTask on-demand upsert logic."""
from cps.services.crawl_service import upsert_crawl_task
from cps.pipeline.orchestrator import _build_price_summary_upsert


def test_upsert_sql_contains_on_conflict():
    """PriceSummary save should use ON CONFLICT ... DO UPDATE."""
    from sqlalchemy.dialects import postgresql
    stmt = _build_price_summary_upsert(
        product_id=1,
        price_type="amazon",
        lowest_price=16900,
        lowest_date=None,
        highest_price=24900,
        highest_date=None,
        current_price=18900,
        current_date=None,
        extraction_id=1,
    )
    compiled = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "ON CONFLICT" in compiled.upper() or "on conflict" in compiled.lower()


def test_crawl_task_upsert_importable():
    """Verify the on-demand crawl upsert helper exists."""
    assert callable(upsert_crawl_task)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_orchestrator_upsert.py -v`
Expected: FAIL

- [ ] **Step 3: Implement upserts**

**A. Modify `src/cps/pipeline/orchestrator.py`** — replace the PriceSummary savepoint block (lines 217-231) with a proper upsert function:

Add imports at top:
```python
from sqlalchemy.dialects.postgresql import insert as pg_insert
```
Also add `func` to the existing sqlalchemy import if not already there:
```python
from sqlalchemy import select, update, func
```

Add module-level function:
```python
def _build_price_summary_upsert(
    product_id: int,
    price_type: str,
    lowest_price: int | None,
    lowest_date: date | None,
    highest_price: int | None,
    highest_date: date | None,
    current_price: int | None,
    current_date: date | None,
    extraction_id: int | None,
    source: str = "ccc_chart",
) -> object:
    """Build PostgreSQL INSERT ... ON CONFLICT DO UPDATE for PriceSummary."""
    stmt = pg_insert(PriceSummary).values(
        product_id=product_id,
        price_type=price_type,
        lowest_price=lowest_price,
        lowest_date=lowest_date,
        highest_price=highest_price,
        highest_date=highest_date,
        current_price=current_price,
        current_date=current_date,
        extraction_id=extraction_id,
        source=source,
    )
    return stmt.on_conflict_do_update(
        index_elements=["product_id", "price_type"],
        set_={
            "lowest_price": stmt.excluded.lowest_price,
            "lowest_date": stmt.excluded.lowest_date,
            "highest_price": stmt.excluded.highest_price,
            "highest_date": stmt.excluded.highest_date,
            "current_price": stmt.excluded.current_price,
            "current_date": stmt.excluded.current_date,
            "extraction_id": stmt.excluded.extraction_id,
            "source": stmt.excluded.source,
            "updated_at": func.now(),
        },
    )
```

Replace the PriceSummary loop in `_process_one` (lines 217-231):
```python
            # Store price summary (UPSERT — update on re-crawl)
            from datetime import date as date_type
            for price_type, summary in pixel_summary.items():
                pts = pixel_data.get(price_type, [])
                dates = [d for d, _ in pts] if pts else []
                stmt = _build_price_summary_upsert(
                    product_id=product.id,
                    price_type=price_type,
                    lowest_price=summary.get("lowest"),
                    lowest_date=min(dates) if dates else None,
                    highest_price=summary.get("highest"),
                    highest_date=max(dates) if dates else None,
                    current_price=summary.get("current"),
                    current_date=dates[-1] if dates else None,
                    extraction_id=run.id,
                )
                await self._session.execute(stmt)
```

**B. Create `src/cps/services/crawl_service.py`** — CrawlTask on-demand upsert:

```python
# src/cps/services/crawl_service.py
"""CrawlTask helpers for on-demand crawl requests (spec Section 7.1)."""
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import CrawlTask


async def upsert_crawl_task(
    session: AsyncSession,
    product_id: int,
    priority: int = 1,
) -> None:
    """Upsert a crawl task: create if not exists, or reset to pending with given priority.

    Per spec: crawl_tasks.product_id has a unique constraint — must use upsert, not insert.
    """
    stmt = pg_insert(CrawlTask).values(
        product_id=product_id,
        priority=priority,
        status="pending",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["product_id"],
        set_={
            "status": "pending",
            "priority": priority,
            "retry_count": 0,
            "error_message": None,
        },
    )
    await session.execute(stmt)
    await session.flush()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_orchestrator_upsert.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add src/cps/pipeline/orchestrator.py src/cps/services/crawl_service.py tests/unit/test_orchestrator_upsert.py
git commit -m "fix: PriceSummary INSERT→UPSERT for re-crawl + CrawlTask on-demand upsert"
```

---

## Chunk 4: Presentation Layer (Messages + Keyboards)

### Task 13: i18n message templates (EN + ES, 3 density levels)

**Files:**
- Create: `src/cps/bot/__init__.py`
- Create: `src/cps/bot/messages.py`
- Create: `tests/unit/test_messages.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_messages.py
"""Tests for message template rendering — EN/ES, 3 density levels."""
from datetime import date

from cps.bot.messages import MessageTemplates, render_price_report
from cps.services.price_service import Density, PriceAnalysis, PriceVerdict


class TestPriceReport:
    ANALYSIS = PriceAnalysis(
        current_price=18900,
        historical_low=16900,
        historical_high=24900,
        historical_low_date=date(2025, 4, 1),
        historical_high_date=date(2025, 1, 1),
        percentile=25,
        trend_30d="dropping",
        verdict=PriceVerdict.GOOD,
    )

    def test_compact_en(self):
        msg = render_price_report(
            title="AirPods Pro 2",
            analysis=self.ANALYSIS,
            density=Density.COMPACT,
            language="en",
        )
        assert "$189" in msg
        assert "$169" in msg
        assert "$249" in msg
        lines = [l for l in msg.strip().split("\n") if l.strip()]
        assert len(lines) <= 4  # compact is 3-4 lines

    def test_standard_en(self):
        msg = render_price_report(
            title="AirPods Pro 2",
            analysis=self.ANALYSIS,
            density=Density.STANDARD,
            language="en",
        )
        assert "AirPods Pro 2" in msg
        assert "$189" in msg
        assert "lower" in msg.lower() or "good" in msg.lower()

    def test_detailed_en(self):
        msg = render_price_report(
            title="AirPods Pro 2",
            analysis=self.ANALYSIS,
            density=Density.DETAILED,
            language="en",
        )
        assert "Percentile" in msg or "25%" in msg
        assert "dropping" in msg.lower() or "▼" in msg

    def test_spanish_compact(self):
        msg = render_price_report(
            title="AirPods Pro 2",
            analysis=self.ANALYSIS,
            density=Density.COMPACT,
            language="es",
        )
        assert "$189" in msg  # prices same in any language
        # Should contain Spanish text
        assert any(w in msg.lower() for w in ["buen", "precio", "bajo"])


class TestTemplates:
    def test_onboarding_en(self):
        t = MessageTemplates("en")
        msg = t.onboarding(
            title="AirPods Pro 2 (USB-C)",
            price_report="Current: $189\nHistorical: $169 - $249",
        )
        assert "BuyPulse" in msg
        assert "Privacy Policy" in msg

    def test_onboarding_es(self):
        t = MessageTemplates("es")
        msg = t.onboarding(
            title="AirPods Pro 2 (USB-C)",
            price_report="Current: $189",
        )
        assert "BuyPulse" in msg

    def test_monitor_limit_reached(self):
        t = MessageTemplates("en")
        msg = t.monitor_limit_reached(current=20, limit=20)
        assert "20/20" in msg

    def test_welcome_back(self):
        t = MessageTemplates("en")
        msg = t.welcome_back(monitor_count=3)
        assert "3" in msg
        assert "Welcome back" in msg or "welcome back" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_messages.py -v`
Expected: FAIL

- [ ] **Step 3: Implement message templates**

Create `src/cps/bot/__init__.py` (empty).

```python
# src/cps/bot/messages.py
"""i18n message templates for BuyPulse Telegram bot.

Two languages: EN, ES. Three density levels: compact, standard, detailed.
All templates are plain functions — no Telegram dependency.
"""
from cps.services.price_service import Density, PriceAnalysis, PriceVerdict, format_price

_VERDICT_EN = {
    PriceVerdict.GREAT: "excellent price",
    PriceVerdict.GOOD: "good price",
    PriceVerdict.FAIR: "fair price",
    PriceVerdict.HIGH: "above average",
    PriceVerdict.VERY_HIGH: "near highest",
}

_VERDICT_ES = {
    PriceVerdict.GREAT: "precio excelente",
    PriceVerdict.GOOD: "buen precio",
    PriceVerdict.FAIR: "precio justo",
    PriceVerdict.HIGH: "por encima del promedio",
    PriceVerdict.VERY_HIGH: "cerca del máximo",
}

_TREND_SYMBOL = {"dropping": "▼", "rising": "▲", "stable": "→"}


def render_price_report(
    title: str,
    analysis: PriceAnalysis,
    density: Density,
    language: str = "en",
) -> str:
    """Render price report at the requested density level."""
    cur = format_price(analysis.current_price)
    low = format_price(analysis.historical_low)
    high = format_price(analysis.historical_high)
    verdict_map = _VERDICT_ES if language == "es" else _VERDICT_EN
    verdict = verdict_map[analysis.verdict]

    if density == Density.COMPACT:
        return (
            f"{title} — {cur} ({verdict})\n"
            f"Historical: {low} - {high}"
        )

    if density == Density.STANDARD:
        pct_label = f"lower {analysis.percentile}%" if analysis.percentile <= 50 else f"upper {100 - analysis.percentile}%"
        return (
            f"{title}\n"
            f"Current: {cur}\n"
            f"Historical: {low} - {high}\n"
            f"This price is in the {pct_label} of its range ({verdict})."
        )

    # Detailed
    low_date = analysis.historical_low_date.strftime("%Y-%m-%d") if analysis.historical_low_date else "N/A"
    high_date = analysis.historical_high_date.strftime("%Y-%m-%d") if analysis.historical_high_date else "N/A"
    trend_sym = _TREND_SYMBOL.get(analysis.trend_30d, "→")
    return (
        f"{title}\n"
        f"Current: {cur}\n"
        f"Historical low: {low} ({low_date})\n"
        f"Historical high: {high} ({high_date})\n"
        f"Percentile: {analysis.percentile}%\n"
        f"30-day trend: {trend_sym} {analysis.trend_30d}\n"
        f"Verdict: {verdict.capitalize()}."
    )


class MessageTemplates:
    """Template factory for a specific language."""

    def __init__(self, language: str = "en") -> None:
        self.lang = language

    def onboarding(self, title: str, price_report: str) -> str:
        if self.lang == "es":
            return (
                f"¡Hola! Soy BuyPulse. Déjame mostrarte lo que hago.\n\n"
                f"{title}\n{price_report}\n\n"
                f"Eso es todo. Envíame cualquier enlace de Amazon o dime qué quieres comprar.\n\n"
                f"Al usar BuyPulse, aceptas nuestra Política de Privacidad."
            )
        return (
            f"Hey! I'm BuyPulse. Let me show you what I do.\n\n"
            f"{title}\n{price_report}\n\n"
            f"That's it. Send me any Amazon link or just tell me "
            f"what you want to buy. I'll track the price for you.\n\n"
            f"By using BuyPulse, you agree to our Privacy Policy."
        )

    def monitor_limit_reached(self, current: int, limit: int) -> str:
        if self.lang == "es":
            return f"Tienes {current}/{limit} monitores. Elimina uno desde /monitors para añadir otro."
        return f"You're at {current}/{limit} monitors. Remove one from /monitors to add a new one."

    def welcome_back(self, monitor_count: int) -> str:
        if self.lang == "es":
            return (
                f"¡Bienvenido de vuelta! Tienes {monitor_count} monitores activos.\n"
                f"Las alertas de ofertas estaban pausadas — ¿quieres reactivarlas?"
            )
        return (
            f"Welcome back! You have {monitor_count} active price monitors.\n"
            f"Deal alerts were paused — want to turn them back on?"
        )

    def fetching_price(self) -> str:
        if self.lang == "es":
            return "No tengo historial de precios para esto aún. Lo estoy buscando — vuelve en unos minutos."
        return "I don't have price history for this yet. I'm fetching it now — check back in a few minutes."

    def crawl_failed(self, asin: str) -> str:
        if self.lang == "es":
            return f"Lo siento, no pude obtener datos de precios para {asin}. Puedes intentar más tarde."
        return f"Sorry, I couldn't fetch price data for {asin}. You can try again later."

    def rate_limited(self) -> str:
        if self.lang == "es":
            return "¡Más despacio! Puedes consultar hasta 50 productos por día."
        return "Slow down! You can check up to 50 products per day."

    def price_alert(
        self, title: str, current: str, target: str, historical_low: str, is_all_time: bool,
    ) -> str:
        atl_note = f" — this matches it!" if is_all_time else ""
        if self.lang == "es":
            atl_note_es = f" — ¡es el mínimo histórico!" if is_all_time else ""
            return (
                f"¡Bajó de precio! {title} ahora está a {current}\n"
                f"Tu objetivo: {target} ✅\n"
                f"Mínimo histórico: {historical_low}{atl_note_es}"
            )
        return (
            f"Price drop! {title} is now {current}\n"
            f"Your target: {target} ✅\n"
            f"Historical low: {historical_low}{atl_note}"
        )

    def deal_push(self, title: str, current: str, original: str, context: str) -> str:
        if self.lang == "es":
            return f"{title} bajó a {current} (era {original})\n{context}"
        return f"{title} dropped to {current} (was {original})\n{context}"

    def downgrade_notice(self, new_frequency: str) -> str:
        freq_en = {"weekly": "weekly", "monthly": "monthly"}
        freq_es = {"weekly": "semanalmente", "monthly": "mensualmente"}
        f = freq_es.get(new_frequency, new_frequency) if self.lang == "es" else freq_en.get(new_frequency, new_frequency)
        if self.lang == "es":
            return f"Te enviaremos ofertas {f} en lugar de diariamente."
        return f"We'll send you deals {f} instead of daily."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_messages.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/bot/__init__.py src/cps/bot/messages.py tests/unit/test_messages.py
git commit -m "feat: add i18n message templates (EN/ES, 3 density levels)"
```

---

### Task 14: Inline keyboard builders

**Files:**
- Create: `src/cps/bot/keyboards.py`
- Create: `tests/unit/test_keyboards.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_keyboards.py
"""Tests for inline keyboard structure — no Telegram runtime needed."""
from cps.bot.keyboards import (
    build_buy_keyboard,
    build_price_report_keyboard,
    build_target_keyboard,
    build_monitor_item_keyboard,
    build_deal_push_keyboard,
    build_reengagement_keyboard,
    build_downgrade_keyboard,
)


class TestBuyKeyboard:
    def test_contains_buy_button(self):
        kb = build_buy_keyboard("https://amazon.com/dp/B08N5WRWNW?tag=foo")
        assert len(kb) >= 1
        assert any("Buy" in btn["text"] or "Amazon" in btn["text"] for row in kb for btn in row)

    def test_buy_button_is_url(self):
        kb = build_buy_keyboard("https://amazon.com/dp/B08N5WRWNW?tag=foo")
        buy_btn = kb[0][0]
        assert "url" in buy_btn


class TestPriceReportKeyboard:
    def test_standard_has_buy_and_alert(self):
        kb = build_price_report_keyboard(
            buy_url="https://amazon.com/dp/B08N5WRWNW?tag=foo",
            asin="B08N5WRWNW",
            density="standard",
        )
        texts = [btn["text"] for row in kb for btn in row]
        assert any("Buy" in t or "Amazon" in t for t in texts)
        assert any("alert" in t.lower() or "set" in t.lower() for t in texts)

    def test_compact_has_detail_expand(self):
        kb = build_price_report_keyboard(
            buy_url="https://amazon.com/dp/B08N5WRWNW?tag=foo",
            asin="B08N5WRWNW",
            density="compact",
        )
        texts = [btn["text"] for row in kb for btn in row]
        assert any("▼" in t or "detail" in t.lower() for t in texts)


class TestTargetKeyboard:
    def test_includes_suggestions_and_custom(self):
        targets = [
            {"label": "Historical low: $169", "price": 16900},
            {"label": "30th pct: $189", "price": 18900},
        ]
        kb = build_target_keyboard("B08N5WRWNW", targets)
        texts = [btn["text"] for row in kb for btn in row]
        assert any("$169" in t for t in texts)
        assert any("Custom" in t or "custom" in t for t in texts)
        assert any("Skip" in t or "skip" in t.lower() for t in texts)


class TestDealPushKeyboard:
    def test_has_buy_and_dismiss(self):
        kb = build_deal_push_keyboard(
            buy_url="https://amazon.com/dp/B08N5WRWNW?tag=foo",
            asin="B08N5WRWNW",
            category="Electronics",
        )
        texts = [btn["text"] for row in kb for btn in row]
        assert any("Buy" in t or "Amazon" in t for t in texts)
        assert any("Stop" in t or "stop" in t.lower() for t in texts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_keyboards.py -v`
Expected: FAIL

- [ ] **Step 3: Implement keyboards**

```python
# src/cps/bot/keyboards.py
"""Inline keyboard builders — returns dicts for easy testing, converted to
InlineKeyboardMarkup at the handler level.

Each builder returns list[list[dict]] where dict has 'text' + ('url' or 'callback_data').
"""


def _btn(text: str, callback_data: str) -> dict:
    return {"text": text, "callback_data": callback_data}


def _url_btn(text: str, url: str) -> dict:
    return {"text": text, "url": url}


def to_telegram_markup(keyboard: list[list[dict]]):
    """Convert our dict-based keyboard to telegram InlineKeyboardMarkup.

    Import telegram only here to keep rest of module dependency-free for testing.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    rows = []
    for row in keyboard:
        buttons = []
        for btn in row:
            if "url" in btn:
                buttons.append(InlineKeyboardButton(text=btn["text"], url=btn["url"]))
            else:
                buttons.append(InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"]))
        rows.append(buttons)
    return InlineKeyboardMarkup(rows)


def build_buy_keyboard(buy_url: str) -> list[list[dict]]:
    return [[_url_btn("Buy on Amazon →", buy_url)]]


def build_price_report_keyboard(
    buy_url: str, asin: str, density: str,
) -> list[list[dict]]:
    """Price report buttons: Buy + detail toggle + set alert."""
    row1 = [_url_btn("Buy on Amazon →", buy_url)]
    row2 = []

    if density == "compact":
        row2.append(_btn("More detail ▼", f"density:standard:{asin}"))
    elif density == "detailed":
        row2.append(_btn("Less detail ▲", f"density:compact:{asin}"))
    else:  # standard
        row2.append(_btn("More detail ▼", f"density:detailed:{asin}"))

    row2.append(_btn("Set alert", f"alert:{asin}"))
    return [row1, row2]


def build_target_keyboard(asin: str, targets: list[dict]) -> list[list[dict]]:
    """Target price selection: preset buttons + custom + skip."""
    rows = []
    for t in targets:
        rows.append([_btn(t["label"], f"target:{asin}:{t['price']}")])
    rows.append([
        _btn("Custom price", f"target_custom:{asin}"),
        _btn("Skip", f"target:{asin}:skip"),
    ])
    return rows


def build_monitor_item_keyboard(asin: str) -> list[list[dict]]:
    return [[_btn("Remove", f"remove_monitor:{asin}")]]


def build_deal_push_keyboard(
    buy_url: str, asin: str, category: str | None,
) -> list[list[dict]]:
    """Deal push: Buy + dismiss (spec Section 4.2)."""
    dismiss_data = f"dismiss_cat:{category}" if category else f"dismiss_asin:{asin}"
    return [
        [_url_btn("Buy on Amazon →", buy_url)],
        [_btn("Stop suggestions like this", dismiss_data)],
    ]


def build_reengagement_keyboard() -> list[list[dict]]:
    return [[
        _btn("Yes, restart deals", "reengage:yes"),
        _btn("No thanks", "reengage:no"),
    ]]


def build_downgrade_keyboard(new_frequency: str) -> list[list[dict]]:
    return [[
        _btn("Keep daily", "downgrade:keep"),
        _btn(f"{new_frequency.capitalize()} is fine", f"downgrade:accept"),
    ]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_keyboards.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/bot/keyboards.py tests/unit/test_keyboards.py
git commit -m "feat: add inline keyboard builders for all bot interactions"
```

---

## Chunk 5: Telegram Bot Handlers

### Task 15: Bot application factory

**Files:**
- Create: `src/cps/bot/app.py`
- Create: `src/cps/bot/handlers/__init__.py`

- [ ] **Step 1: Create the application factory**

```python
# src/cps/bot/app.py
"""Bot Application factory — creates and configures the Telegram bot.

Stores shared resources (session_factory, settings, ai_client) in bot_data
so handlers can access them via context.bot_data.
"""
import structlog
from telegram.ext import Application

from cps.ai.client import AIClient
from cps.config import Settings
from cps.db.session import create_session_factory

log = structlog.get_logger()


async def post_init(application: Application) -> None:
    """Called after Application.initialize() — set up shared resources."""
    settings: Settings = application.bot_data["settings"]
    application.bot_data["session_factory"] = create_session_factory(settings.database_url)
    application.bot_data["ai_client"] = AIClient(api_key=settings.anthropic_api_key)
    log.info("bot_initialized", affiliate_tag=settings.affiliate_tag)


async def post_shutdown(application: Application) -> None:
    """Clean up on shutdown."""
    sf = application.bot_data.get("session_factory")
    if sf:
        engine = sf.kw.get("bind")
        if engine:
            await engine.dispose()
    log.info("bot_shutdown")


def create_bot_app(settings: Settings) -> Application:
    """Build the fully configured bot Application."""
    from cps.bot.handlers import register_handlers

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings
    register_handlers(app)
    return app
```

```python
# src/cps/bot/handlers/__init__.py
"""Register all bot handlers in correct priority order."""
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters


def register_handlers(app: Application) -> None:
    """Wire all handlers to the application.

    Order matters: commands first, then callback queries, then catch-all text.
    """
    from cps.bot.handlers.start import start_command
    from cps.bot.handlers.monitors import monitors_command
    from cps.bot.handlers.settings import settings_command, language_command, help_command
    from cps.bot.handlers.price_check import handle_text_message
    from cps.bot.handlers.callbacks import handle_callback

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("monitors", monitors_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("help", help_command))

    # Callback queries (inline buttons)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Catch-all text messages (URL/ASIN/NLP)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
```

- [ ] **Step 2: Verify imports work**

Run: `uv run python -c "from cps.bot.app import create_bot_app; print('OK')"`
Expected: `OK` (may warn about missing handler modules — that's fine, we create them next)

- [ ] **Step 3: Commit**

```bash
git add src/cps/bot/app.py src/cps/bot/handlers/__init__.py
git commit -m "feat: add bot application factory and handler registration"
```

---

### Task 16: /start onboarding handler

**Files:**
- Create: `src/cps/bot/handlers/start.py`
- Create: `tests/unit/test_handlers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_handlers.py
"""Tests for bot handlers — mocked Telegram Update + Context."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_update(text="/start", user_id=12345, username="testuser", first_name="Test"):
    """Build a mock Telegram Update."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = username
    update.effective_user.first_name = first_name
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.callback_query = None
    return update


def _make_context(settings=None):
    """Build a mock CallbackContext with bot_data."""
    context = MagicMock()
    context.bot_data = {
        "settings": settings or MagicMock(affiliate_tag="test-20", demo_asin="B0D1XD1ZV3"),
        "session_factory": MagicMock(),
        "ai_client": MagicMock(),
    }
    return context


class TestStartHandler:
    @patch("cps.bot.handlers.start.get_session")
    async def test_sends_onboarding_message(self, mock_get_session):
        from cps.bot.handlers.start import start_command

        update = _make_update("/start")
        context = _make_context()

        # Mock DB session
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock user service
        with patch("cps.bot.handlers.start.UserService") as MockUserService:
            mock_user_svc = AsyncMock()
            mock_user_svc.get_or_create = AsyncMock(return_value=MagicMock(language="en"))
            MockUserService.return_value = mock_user_svc

            # Mock product lookup for demo
            mock_session.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )

            await start_command(update, context)

        update.message.reply_text.assert_called_once()
        msg = update.message.reply_text.call_args[0][0]
        assert "BuyPulse" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_handlers.py::TestStartHandler -v`
Expected: FAIL

- [ ] **Step 3: Implement /start handler**

```python
# src/cps/bot/handlers/start.py
"""Onboarding handler: /start → demo product → immediate value.

Per spec Section 1: one message, real data, affiliate link, privacy notice.
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from cps.bot.keyboards import build_buy_keyboard, to_telegram_markup
from cps.bot.messages import MessageTemplates, render_price_report
from cps.db.models import Product, PriceSummary
from cps.db.session import get_session
from cps.services.affiliate import build_product_link
from cps.services.price_service import Density, analyze_price
from cps.services.user_service import UserService

from sqlalchemy import select

log = structlog.get_logger()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — onboarding with demo product."""
    settings = context.bot_data["settings"]
    session_factory = context.bot_data["session_factory"]
    tg_user = update.effective_user

    async with get_session(session_factory) as session:
        user_svc = UserService(session)
        user = await user_svc.get_or_create(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
        )
        await user_svc.record_interaction(user)

        # Try to load demo product
        templates = MessageTemplates(user.language)
        demo_asin = settings.demo_asin

        result = await session.execute(
            select(Product).where(Product.asin == demo_asin)
        )
        product = result.scalar_one_or_none()

        if product is not None:
            # Load price summary
            ps_result = await session.execute(
                select(PriceSummary).where(
                    PriceSummary.product_id == product.id,
                    PriceSummary.price_type == "amazon",
                )
            )
            summary = ps_result.scalar_one_or_none()

            if summary and summary.current_price:
                analysis = analyze_price(
                    current_price=summary.current_price,
                    price_history=[],  # simplified for onboarding
                    lowest_price=summary.lowest_price or summary.current_price,
                    lowest_date=summary.lowest_date,
                    highest_price=summary.highest_price or summary.current_price,
                    highest_date=summary.highest_date,
                )
                price_report = render_price_report(
                    title=product.title or demo_asin,
                    analysis=analysis,
                    density=Density.STANDARD,
                    language=user.language,
                )
                buy_url = build_product_link(demo_asin, settings.affiliate_tag)
                kb = to_telegram_markup(build_buy_keyboard(buy_url))
                msg = templates.onboarding(title=product.title or demo_asin, price_report=price_report)
                await update.message.reply_text(msg, reply_markup=kb)
                await session.commit()
                return

        # Fallback: no demo data available
        msg = templates.onboarding(
            title="",
            price_report="Send me any Amazon link or tell me what you want to buy.",
        )
        await update.message.reply_text(msg)
        await session.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_handlers.py::TestStartHandler -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/bot/handlers/start.py tests/unit/test_handlers.py
git commit -m "feat: add /start onboarding handler with demo product"
```

---

### Task 17: Price check handler (URL/ASIN/NLP dispatch)

**Files:**
- Create: `src/cps/bot/handlers/price_check.py`
- Modify: `tests/unit/test_handlers.py` (add tests)

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_handlers.py`:

```python
class TestPriceCheckHandler:
    @patch("cps.bot.handlers.price_check.get_session")
    async def test_url_input_triggers_price_lookup(self, mock_get_session):
        from cps.bot.handlers.price_check import handle_text_message

        update = _make_update("https://amazon.com/dp/B08N5WRWNW")
        context = _make_context()

        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock product found in DB
        product = MagicMock(id=1, asin="B08N5WRWNW", title="AirPods Pro 2")
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=product))
        )

        with patch("cps.bot.handlers.price_check.UserService") as MockUS, \
             patch("cps.bot.handlers.price_check._send_price_report") as mock_send:
            MockUS.return_value.get_or_create = AsyncMock(
                return_value=MagicMock(language="en", density_preference="standard")
            )
            MockUS.return_value.record_interaction = AsyncMock()
            mock_send.return_value = None

            await handle_text_message(update, context)
            mock_send.assert_called_once()

    @patch("cps.bot.handlers.price_check.get_session")
    async def test_nlp_input_triggers_search(self, mock_get_session):
        from cps.bot.handlers.price_check import handle_text_message

        update = _make_update("How much are AirPods?")
        context = _make_context()

        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("cps.bot.handlers.price_check.UserService") as MockUS, \
             patch("cps.bot.handlers.price_check._handle_nlp_search") as mock_nlp:
            MockUS.return_value.get_or_create = AsyncMock(
                return_value=MagicMock(language="en", density_preference="standard")
            )
            MockUS.return_value.record_interaction = AsyncMock()
            mock_nlp.return_value = None

            await handle_text_message(update, context)
            mock_nlp.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_handlers.py::TestPriceCheckHandler -v`
Expected: FAIL

- [ ] **Step 3: Implement price check handler**

```python
# src/cps/bot/handlers/price_check.py
"""Handle text messages: classify as URL/ASIN/NLP → dispatch to price lookup or search.

Per spec Section 2.2: URL regex → ASIN regex → natural language.
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from cps.bot.keyboards import build_price_report_keyboard, to_telegram_markup
from cps.bot.messages import MessageTemplates, render_price_report
from cps.bot.rate_limiter import check_rate_limit
from cps.db.models import PriceHistory, PriceSummary, Product
from cps.db.session import get_session
from cps.services.affiliate import build_product_link
from cps.services.asin_parser import InputType, parse_input
from cps.services.crawl_service import upsert_crawl_task
from cps.services.price_service import Density, analyze_price
from cps.services.search_service import SearchService
from cps.services.user_service import UserService

from sqlalchemy import select

log = structlog.get_logger()


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main message handler — dispatch based on input type."""
    settings = context.bot_data["settings"]
    session_factory = context.bot_data["session_factory"]
    text = update.message.text.strip()

    async with get_session(session_factory) as session:
        user_svc = UserService(session)
        user = await user_svc.get_or_create(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        await user_svc.record_interaction(user)

        parsed = parse_input(text)

        if parsed.input_type in (InputType.URL, InputType.ASIN):
            await _handle_asin_lookup(update, context, session, user, parsed.asin, settings)
        else:
            await _handle_nlp_search(update, context, session, user, parsed.query, settings)

        await session.commit()


async def _handle_asin_lookup(update, context, session, user, asin, settings):
    """Look up product by ASIN → show price report or trigger on-demand crawl."""
    result = await session.execute(
        select(Product).where(Product.asin == asin)
    )
    product = result.scalar_one_or_none()

    if product is None:
        # Create product + trigger on-demand crawl
        product = Product(asin=asin)
        session.add(product)
        await session.flush()
        await upsert_crawl_task(session, product.id, priority=1)
        templates = MessageTemplates(user.language)
        await update.message.reply_text(templates.fetching_price())
        return

    await _send_price_report(update, session, user, product, settings)


async def _handle_nlp_search(update, context, session, user, query, settings):
    """Use AI to extract search intent → search waterfall."""
    ai_client = context.bot_data["ai_client"]
    search_query = await ai_client.extract_search_intent(query)

    search_svc = SearchService(session, settings.affiliate_tag)
    result = await search_svc.search(search_query)

    if result.product is not None:
        await _send_price_report(update, session, user, result.product, settings)
    elif result.fallback_url:
        templates = MessageTemplates(user.language)
        msg = (
            "I couldn't find that exact product. "
            "Here's an Amazon search link — send me the product link from there."
            if user.language == "en" else
            "No encontré ese producto exacto. "
            "Aquí tienes un enlace de búsqueda — envíame el enlace del producto."
        )
        from cps.bot.keyboards import build_buy_keyboard, to_telegram_markup
        kb = to_telegram_markup(build_buy_keyboard(result.fallback_url))
        await update.message.reply_text(msg, reply_markup=kb)


async def _send_price_report(update, session, user, product, settings):
    """Build and send price report for a product."""
    # Load price summary
    ps_result = await session.execute(
        select(PriceSummary).where(
            PriceSummary.product_id == product.id,
            PriceSummary.price_type == "amazon",
        )
    )
    summary = ps_result.scalar_one_or_none()

    if summary is None or summary.current_price is None:
        # No price data — trigger crawl
        await upsert_crawl_task(session, product.id, priority=1)
        templates = MessageTemplates(user.language)
        await update.message.reply_text(templates.fetching_price())
        return

    # Load full price history for percentile calculation
    ph_result = await session.execute(
        select(PriceHistory.price_cents).where(
            PriceHistory.product_id == product.id,
            PriceHistory.price_type == "amazon",
        )
    )
    all_prices = [row[0] for row in ph_result.all()]

    # Build history tuples for trend calculation
    ph_full = await session.execute(
        select(PriceHistory.recorded_date, PriceHistory.price_cents).where(
            PriceHistory.product_id == product.id,
            PriceHistory.price_type == "amazon",
        ).order_by(PriceHistory.recorded_date)
    )
    history = [(row[0], row[1]) for row in ph_full.all()]

    analysis = analyze_price(
        current_price=summary.current_price,
        price_history=history,
        lowest_price=summary.lowest_price or summary.current_price,
        lowest_date=summary.lowest_date,
        highest_price=summary.highest_price or summary.current_price,
        highest_date=summary.highest_date,
    )

    density = Density(user.density_preference)
    msg = render_price_report(
        title=product.title or product.asin,
        analysis=analysis,
        density=density,
        language=user.language,
    )

    buy_url = build_product_link(product.asin, settings.affiliate_tag)
    kb = to_telegram_markup(
        build_price_report_keyboard(buy_url, product.asin, density.value)
    )
    await update.message.reply_text(msg, reply_markup=kb)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_handlers.py::TestPriceCheckHandler -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/bot/handlers/price_check.py tests/unit/test_handlers.py
git commit -m "feat: add price check handler with URL/ASIN/NLP dispatch"
```

---

### Task 18: Callback query handlers (inline buttons)

**Files:**
- Create: `src/cps/bot/handlers/callbacks.py`
- Modify: `tests/unit/test_handlers.py` (add callback tests)

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_handlers.py`:

```python
def _make_callback_update(data, user_id=12345):
    """Build a mock Telegram Update with callback_query."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.message.reply_text = AsyncMock()
    return update


class TestCallbackHandler:
    @patch("cps.bot.handlers.callbacks.get_session")
    async def test_density_toggle(self, mock_get_session):
        from cps.bot.handlers.callbacks import handle_callback

        update = _make_callback_update("density:detailed:B08N5WRWNW")
        context = _make_context()

        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("cps.bot.handlers.callbacks._handle_density_toggle") as mock_toggle:
            mock_toggle.return_value = None
            await handle_callback(update, context)
            mock_toggle.assert_called_once()

    @patch("cps.bot.handlers.callbacks.get_session")
    async def test_target_price_selection(self, mock_get_session):
        from cps.bot.handlers.callbacks import handle_callback

        update = _make_callback_update("target:B08N5WRWNW:16900")
        context = _make_context()

        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("cps.bot.handlers.callbacks._handle_target_selection") as mock_target:
            mock_target.return_value = None
            await handle_callback(update, context)
            mock_target.assert_called_once()

    @patch("cps.bot.handlers.callbacks.get_session")
    async def test_dismiss_deal(self, mock_get_session):
        from cps.bot.handlers.callbacks import handle_callback

        update = _make_callback_update("dismiss_cat:Electronics")
        context = _make_context()

        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("cps.bot.handlers.callbacks._handle_dismiss") as mock_dismiss:
            mock_dismiss.return_value = None
            await handle_callback(update, context)
            mock_dismiss.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_handlers.py::TestCallbackHandler -v`
Expected: FAIL

- [ ] **Step 3: Implement callback handler**

```python
# src/cps/bot/handlers/callbacks.py
"""Handle all inline button callbacks.

Callback data format: "action:param1:param2"
Actions: density, alert, target, target_custom, remove_monitor,
         dismiss_cat, dismiss_asin, reengage, downgrade, clicked
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from cps.db.models import (
    DealDismissal,
    NotificationLog,
    PriceMonitor,
    Product,
    TelegramUser,
)
from cps.db.session import get_session
from cps.services.monitor_service import MonitorService
from cps.services.user_service import NotificationState, UserService

from sqlalchemy import select

log = structlog.get_logger()


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route callback queries to appropriate handlers."""
    query = update.callback_query
    await query.answer()

    data = query.data
    settings = context.bot_data["settings"]
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        if data.startswith("density:"):
            await _handle_density_toggle(update, context, session, data, settings)
        elif data.startswith("alert:"):
            await _handle_alert_setup(update, context, session, data, settings)
        elif data.startswith("target:"):
            await _handle_target_selection(update, context, session, data, settings)
        elif data.startswith("target_custom:"):
            await _handle_custom_target(update, context, session, data)
        elif data.startswith("remove_monitor:"):
            await _handle_remove_monitor(update, context, session, data)
        elif data.startswith("dismiss_cat:") or data.startswith("dismiss_asin:"):
            await _handle_dismiss(update, context, session, data)
        elif data.startswith("reengage:"):
            await _handle_reengagement(update, context, session, data)
        elif data.startswith("downgrade:"):
            await _handle_downgrade_response(update, context, session, data)
        elif data.startswith("clicked:"):
            await _handle_click_tracking(session, data, update.effective_user.id)

        await session.commit()


async def _handle_density_toggle(update, context, session, data, settings):
    """Toggle price report density for current message (per-query, not persisted)."""
    parts = data.split(":")
    density = parts[1]
    asin = parts[2]

    # Re-render the price report at new density
    # Import here to avoid circular imports
    from cps.bot.handlers.price_check import _send_price_report

    result = await session.execute(select(Product).where(Product.asin == asin))
    product = result.scalar_one_or_none()
    if product is None:
        return

    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(update.effective_user.id)
    if user is None:
        return

    # Temporarily override density for this render
    original_density = user.density_preference
    user.density_preference = density
    # Re-send as new message (editing inline keyboard message)
    from cps.bot.handlers.price_check import _send_price_report
    await _send_price_report(update.callback_query, session, user, product, settings)
    user.density_preference = original_density  # restore


async def _handle_alert_setup(update, context, session, data, settings):
    """Show target price selection buttons."""
    asin = data.split(":")[1]

    result = await session.execute(select(Product).where(Product.asin == asin))
    product = result.scalar_one_or_none()
    if product is None:
        return

    from cps.services.price_service import suggest_targets, PriceAnalysis
    from cps.db.models import PriceSummary, PriceHistory
    from cps.bot.keyboards import build_target_keyboard, to_telegram_markup

    ps_result = await session.execute(
        select(PriceSummary).where(
            PriceSummary.product_id == product.id,
            PriceSummary.price_type == "amazon",
        )
    )
    summary = ps_result.scalar_one_or_none()
    if summary is None:
        return

    ph_result = await session.execute(
        select(PriceHistory.price_cents).where(
            PriceHistory.product_id == product.id,
            PriceHistory.price_type == "amazon",
        )
    )
    all_prices = [row[0] for row in ph_result.all()]

    from cps.services.price_service import analyze_price
    analysis = analyze_price(
        current_price=summary.current_price or 0,
        price_history=[],
        lowest_price=summary.lowest_price or 0,
        lowest_date=summary.lowest_date,
        highest_price=summary.highest_price or 0,
        highest_date=summary.highest_date,
    )
    targets = suggest_targets(analysis, all_prices)
    title = product.title or asin

    kb = to_telegram_markup(build_target_keyboard(asin, targets))
    msg = f"Set a price alert for {title}:"
    await update.callback_query.message.reply_text(msg, reply_markup=kb)


async def _handle_target_selection(update, context, session, data, settings):
    """User tapped a target price button → create monitor immediately."""
    parts = data.split(":")
    asin = parts[1]
    price_str = parts[2]

    target_price = None if price_str == "skip" else int(price_str)

    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(update.effective_user.id)
    if user is None:
        return

    result = await session.execute(select(Product).where(Product.asin == asin))
    product = result.scalar_one_or_none()
    if product is None:
        return

    mon_svc = MonitorService(session)
    monitor = await mon_svc.create_monitor(
        user_id=user.id,
        product_id=product.id,
        monitor_limit=user.monitor_limit,
        target_price=target_price,
    )

    if monitor is None:
        from cps.bot.messages import MessageTemplates
        templates = MessageTemplates(user.language)
        count = await mon_svc.count_active(user.id)
        await update.callback_query.message.reply_text(
            templates.monitor_limit_reached(count, user.monitor_limit)
        )
        return

    if target_price:
        from cps.services.price_service import format_price
        await update.callback_query.message.reply_text(
            f"✅ Monitoring {product.title or asin} — alert at {format_price(target_price)}"
        )
    else:
        await update.callback_query.message.reply_text(
            f"✅ Monitoring {product.title or asin} — no target price set"
        )


async def _handle_custom_target(update, context, session, data):
    """Prompt user to type a custom price."""
    asin = data.split(":")[1]
    await update.callback_query.message.reply_text(
        f"Type your target price in dollars (e.g., 159.99):"
    )
    # TODO: Set a conversation state to capture the next message as a custom price
    # For V1, we'll handle this in the text handler by checking for pending custom targets


async def _handle_remove_monitor(update, context, session, data):
    """Remove a monitor from /monitors list."""
    asin = data.split(":")[1]

    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(update.effective_user.id)
    if user is None:
        return

    result = await session.execute(select(Product).where(Product.asin == asin))
    product = result.scalar_one_or_none()
    if product is None:
        return

    mon_svc = MonitorService(session)
    removed = await mon_svc.remove_monitor(user.id, product.id)
    if removed:
        await update.callback_query.message.reply_text(f"Removed monitor for {product.title or asin}.")
    else:
        await update.callback_query.message.reply_text("Monitor not found.")


async def _handle_dismiss(update, context, session, data):
    """Dismiss deal suggestions by category or ASIN (spec Section 4.2)."""
    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(update.effective_user.id)
    if user is None:
        return

    if data.startswith("dismiss_cat:"):
        category = data.split(":", 1)[1]
        dismissal = DealDismissal(user_id=user.id, dismissed_category=category)
    else:
        asin = data.split(":", 1)[1]
        dismissal = DealDismissal(user_id=user.id, dismissed_asin=asin)

    session.add(dismissal)
    await session.flush()
    await update.callback_query.message.reply_text("Got it — you won't see suggestions like this again.")


async def _handle_reengagement(update, context, session, data):
    """Handle re-engagement response (spec Section 4.4)."""
    choice = data.split(":")[1]
    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(update.effective_user.id)
    if user is None:
        return

    if choice == "yes":
        await user_svc.transition_state(user, NotificationState.ACTIVE)
        await update.callback_query.message.reply_text("Deal alerts reactivated! 🎉")
    else:
        await update.callback_query.message.reply_text("No problem — your price monitors are still active.")


async def _handle_downgrade_response(update, context, session, data):
    """Handle downgrade notification response."""
    choice = data.split(":")[1]
    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(update.effective_user.id)
    if user is None:
        return

    if choice == "keep":
        await user_svc.transition_state(user, NotificationState.ACTIVE)
        await update.callback_query.message.reply_text("Keeping daily deal alerts.")


async def _handle_click_tracking(session, data, telegram_user_id):
    """Track affiliate link clicks (inline button taps only)."""
    notification_id = data.split(":")[1]
    try:
        nid = int(notification_id)
        result = await session.execute(
            select(NotificationLog).where(NotificationLog.id == nid)
        )
        notification = result.scalar_one_or_none()
        if notification:
            notification.clicked = True
    except (ValueError, IndexError):
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_handlers.py::TestCallbackHandler -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/bot/handlers/callbacks.py tests/unit/test_handlers.py
git commit -m "feat: add callback query handler for all inline button actions"
```

---

### Task 19: Command handlers (/monitors, /settings, /language, /help)

**Files:**
- Create: `src/cps/bot/handlers/monitors.py`
- Create: `src/cps/bot/handlers/settings.py`

- [ ] **Step 1: Implement /monitors handler**

```python
# src/cps/bot/handlers/monitors.py
"""/monitors command — list all active monitors with current prices."""
import structlog
from telegram import Update
from telegram.ext import ContextTypes

from cps.bot.keyboards import build_monitor_item_keyboard, to_telegram_markup
from cps.db.models import PriceSummary
from cps.db.session import get_session
from cps.services.monitor_service import MonitorService
from cps.services.price_service import format_price
from cps.services.user_service import UserService

from sqlalchemy import select

log = structlog.get_logger()


async def monitors_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List user's active monitors with prices and [Remove] buttons."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        user_svc = UserService(session)
        user = await user_svc.get_or_create(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
        )
        await user_svc.record_interaction(user)

        mon_svc = MonitorService(session)
        monitors = await mon_svc.list_active(user.id)
        count = len(monitors)

        if count == 0:
            await update.message.reply_text(
                "You have no active monitors. Send me an Amazon link to start tracking!"
                if user.language == "en" else
                "No tienes monitores activos. ¡Envíame un enlace de Amazon para empezar!"
            )
            await session.commit()
            return

        header = f"Your monitors ({count}/{user.monitor_limit}):\n"
        lines = [header]

        for i, mon in enumerate(monitors, 1):
            product = mon.product
            title = product.title or product.asin if product else "Unknown"

            # Get current price
            ps_result = await session.execute(
                select(PriceSummary).where(
                    PriceSummary.product_id == mon.product_id,
                    PriceSummary.price_type == "amazon",
                )
            )
            summary = ps_result.scalar_one_or_none()
            price_str = format_price(summary.current_price) if summary and summary.current_price else "N/A"
            target_str = f" (target: {format_price(mon.target_price)})" if mon.target_price else " (no target)"

            lines.append(f"{i}. {title} — {price_str}{target_str}")

        msg = "\n".join(lines)
        await update.message.reply_text(msg)

        # Send individual remove buttons
        for mon in monitors:
            product = mon.product
            asin = product.asin if product else "?"
            kb = to_telegram_markup(build_monitor_item_keyboard(asin))
            title = product.title or asin if product else "?"
            await update.message.reply_text(f"  {title}", reply_markup=kb)

        await session.commit()
```

- [ ] **Step 2: Implement /settings, /language, /help handlers**

```python
# src/cps/bot/handlers/settings.py
"""/settings, /language, /help command handlers."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from cps.db.session import get_session
from cps.services.user_service import UserService


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show settings menu."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        user_svc = UserService(session)
        user = await user_svc.get_or_create(telegram_id=update.effective_user.id)
        await user_svc.record_interaction(user)

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Compact", callback_data="set_density:compact"),
             InlineKeyboardButton("Standard", callback_data="set_density:standard"),
             InlineKeyboardButton("Detailed", callback_data="set_density:detailed")],
            [InlineKeyboardButton("English", callback_data="set_lang:en"),
             InlineKeyboardButton("Español", callback_data="set_lang:es")],
            [InlineKeyboardButton("Pause deal alerts", callback_data="pause_deals")],
            [InlineKeyboardButton("Delete my data", callback_data="delete_data")],
        ])

        current = f"Density: {user.density_preference} | Language: {user.language}"
        await update.message.reply_text(f"Settings\n{current}", reply_markup=kb)
        await session.commit()


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick language switch: EN ↔ ES."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        user_svc = UserService(session)
        user = await user_svc.get_or_create(telegram_id=update.effective_user.id)
        await user_svc.record_interaction(user)

        new_lang = "es" if user.language == "en" else "en"
        await user_svc.update_language(user, new_lang)

        labels = {"en": "English", "es": "Español"}
        await update.message.reply_text(f"Language set to {labels[new_lang]}.")
        await session.commit()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """One-screen help with examples."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        user_svc = UserService(session)
        user = await user_svc.get_or_create(telegram_id=update.effective_user.id)

        if user.language == "es":
            msg = (
                "📖 Cómo usar BuyPulse:\n\n"
                "• Envía un enlace de Amazon → obtén el precio + historial\n"
                "• Envía un ASIN (ej: B08N5WRWNW) → consulta directa\n"
                "• Escribe un producto (ej: 'AirPods Pro') → búsqueda\n\n"
                "Comandos:\n"
                "/monitors — ver tus alertas\n"
                "/settings — idioma, densidad, alertas\n"
                "/language — cambiar idioma EN ↔ ES\n"
                "/help — esta ayuda"
            )
        else:
            msg = (
                "📖 How to use BuyPulse:\n\n"
                "• Send an Amazon link → get price + history\n"
                "• Send an ASIN (e.g., B08N5WRWNW) → direct lookup\n"
                "• Type a product (e.g., 'AirPods Pro') → search\n\n"
                "Commands:\n"
                "/monitors — view your price alerts\n"
                "/settings — language, density, deal alerts\n"
                "/language — switch EN ↔ ES\n"
                "/help — this help screen"
            )

        await update.message.reply_text(msg)
        await session.commit()
```

- [ ] **Step 3: Verify no import errors**

Run: `uv run python -c "from cps.bot.handlers.monitors import monitors_command; from cps.bot.handlers.settings import settings_command, language_command, help_command; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/cps/bot/handlers/monitors.py src/cps/bot/handlers/settings.py
git commit -m "feat: add /monitors, /settings, /language, /help command handlers"
```

---

## Chunk 6: Rate Limiting, Notifications, and Background Jobs

### Task 20: Rate limiter + blocked user handling

**Files:**
- Create: `src/cps/bot/rate_limiter.py`
- Create: `tests/unit/test_rate_limiter_bot.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_rate_limiter_bot.py
"""Tests for per-user rate limiting (spec Section 7.2)."""
import time

from cps.bot.rate_limiter import RateLimitResult, check_rate_limit


class TestRateLimit:
    def test_first_message_allowed(self):
        state: dict = {}
        result = check_rate_limit(state, user_id=1, now=time.time())
        assert result == RateLimitResult.ALLOWED

    def test_11th_message_in_one_minute_blocked(self):
        state: dict = {}
        now = time.time()
        for _ in range(10):
            check_rate_limit(state, user_id=1, now=now)
        result = check_rate_limit(state, user_id=1, now=now + 0.1)
        assert result == RateLimitResult.MSG_RATE_EXCEEDED

    def test_messages_allowed_after_minute_passes(self):
        state: dict = {}
        now = time.time()
        for _ in range(10):
            check_rate_limit(state, user_id=1, now=now)
        result = check_rate_limit(state, user_id=1, now=now + 61)
        assert result == RateLimitResult.ALLOWED

    def test_51st_query_per_day_blocked(self):
        state: dict = {}
        now = time.time()
        for i in range(50):
            # Space messages 7 seconds apart to avoid msg/min limit
            check_rate_limit(state, user_id=1, now=now + i * 7)
        result = check_rate_limit(state, user_id=1, now=now + 50 * 7)
        assert result == RateLimitResult.DAILY_LIMIT_EXCEEDED

    def test_different_users_independent(self):
        state: dict = {}
        now = time.time()
        for _ in range(10):
            check_rate_limit(state, user_id=1, now=now)
        result = check_rate_limit(state, user_id=2, now=now)
        assert result == RateLimitResult.ALLOWED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_rate_limiter_bot.py -v`
Expected: FAIL

- [ ] **Step 3: Implement rate limiter**

```python
# src/cps/bot/rate_limiter.py
"""Per-user rate limiting (spec Section 7.2).

| Limit                         | Value | Purpose                |
|-------------------------------|-------|------------------------|
| Messages per minute per user  | 10    | Prevent spam/abuse     |
| Price queries per day per user| 50    | Control AI API cost    |
"""
from collections import defaultdict
from enum import Enum

_MSG_PER_MINUTE = 10
_QUERIES_PER_DAY = 50
_MINUTE = 60.0
_DAY = 86400.0


class RateLimitResult(str, Enum):
    ALLOWED = "allowed"
    MSG_RATE_EXCEEDED = "msg_rate_exceeded"
    DAILY_LIMIT_EXCEEDED = "daily_limit_exceeded"


def check_rate_limit(state: dict, user_id: int, now: float) -> RateLimitResult:
    """Check and update rate limit state. Pure function with external state dict.

    state format: {user_id: {"minute_timestamps": [...], "day_start": float, "day_count": int}}
    """
    if user_id not in state:
        state[user_id] = {"minute_timestamps": [], "day_start": now, "day_count": 0}

    user_state = state[user_id]

    # Clean old minute timestamps
    cutoff = now - _MINUTE
    user_state["minute_timestamps"] = [
        ts for ts in user_state["minute_timestamps"] if ts > cutoff
    ]

    # Check msg/min
    if len(user_state["minute_timestamps"]) >= _MSG_PER_MINUTE:
        return RateLimitResult.MSG_RATE_EXCEEDED

    # Reset daily counter if day passed
    if now - user_state["day_start"] > _DAY:
        user_state["day_start"] = now
        user_state["day_count"] = 0

    # Check daily limit
    if user_state["day_count"] >= _QUERIES_PER_DAY:
        return RateLimitResult.DAILY_LIMIT_EXCEEDED

    # Allow and record
    user_state["minute_timestamps"].append(now)
    user_state["day_count"] += 1
    return RateLimitResult.ALLOWED
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_rate_limiter_bot.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/bot/rate_limiter.py tests/unit/test_rate_limiter_bot.py
git commit -m "feat: add per-user rate limiter (10 msg/min, 50 queries/day)"
```

---

### Task 21: Notification service (Telegram push + cooldown + blocked handling)

**Files:**
- Create: `src/cps/services/notification_service.py`
- Create: `tests/unit/test_notification_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_notification_service.py
"""Tests for notification dispatch with cooldown and blocked handling."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import Forbidden

from cps.services.notification_service import NotificationService


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    return bot


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_bot, mock_session):
    return NotificationService(mock_bot, mock_session)


class TestSendNotification:
    async def test_sends_message(self, service, mock_bot):
        result = await service.send(
            telegram_id=12345, text="Price drop!", notification_type="price_alert"
        )
        assert result is True
        mock_bot.send_message.assert_called_once()

    async def test_handles_forbidden_marks_blocked(self, service, mock_bot, mock_session):
        mock_bot.send_message.side_effect = Forbidden("blocked by user")

        with pytest.raises(Forbidden):
            await service.send(telegram_id=12345, text="test", notification_type="system")
        # Verify it signals the user should be marked blocked
        # (actual DB marking done by caller)

    async def test_logs_notification(self, service, mock_session):
        await service.send(
            telegram_id=12345,
            text="Deal alert",
            notification_type="deal_push",
            product_id=99,
            affiliate_tag="buypulse-20",
        )
        mock_session.add.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_notification_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement notification service**

```python
# src/cps/services/notification_service.py
"""Notification dispatch: send Telegram messages, log them, handle blocked users.

Per spec Section 7.3: Forbidden → mark blocked, stop all sends.
"""
import structlog
from telegram import Bot, InlineKeyboardMarkup
from telegram.error import Forbidden

from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import NotificationLog

log = structlog.get_logger()


class NotificationService:
    def __init__(self, bot: Bot, session: AsyncSession) -> None:
        self._bot = bot
        self._session = session

    async def send(
        self,
        telegram_id: int,
        text: str,
        notification_type: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        product_id: int | None = None,
        affiliate_tag: str | None = None,
    ) -> bool:
        """Send a Telegram message and log it.

        Raises Forbidden if user blocked the bot (caller must handle).
        Returns True on success.
        """
        await self._bot.send_message(
            chat_id=telegram_id,
            text=text,
            reply_markup=reply_markup,
        )

        # Log notification
        log_entry = NotificationLog(
            user_id=0,  # caller should set the correct user_id after
            product_id=product_id,
            notification_type=notification_type,
            message_text=text[:1000],  # truncate for storage
            affiliate_tag=affiliate_tag,
        )
        self._session.add(log_entry)

        log.info("notification_sent", telegram_id=telegram_id, type=notification_type)
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_notification_service.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/services/notification_service.py tests/unit/test_notification_service.py
git commit -m "feat: add notification service with Telegram push and logging"
```

---

### Task 22: Interaction tracking service

**Files:**
- Create: `src/cps/services/interaction_service.py`
- Create: `tests/unit/test_interaction_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_interaction_service.py
"""Tests for user interaction tracking and behavior pattern queries."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.services.interaction_service import InteractionService


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    return InteractionService(mock_session)


class TestRecordInteraction:
    async def test_records_search(self, service, mock_session):
        await service.record(user_id=1, interaction_type="search", payload="robot vacuum")
        mock_session.add.assert_called_once()

    async def test_records_button_click(self, service, mock_session):
        await service.record(user_id=1, interaction_type="button_click", payload="buy:B08N5WRWNW")
        mock_session.add.assert_called_once()


class TestBehaviorQuery:
    async def test_repeated_search_detection(self, service, mock_session):
        # Mock: user searched "robot vacuum" 3 times in 7 days
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("robot vacuum", 3),
            ("airpods", 1),
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)

        patterns = await service.get_repeated_searches(user_id=1, min_count=3, days=7)
        assert len(patterns) >= 1
        assert patterns[0][0] == "robot vacuum"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_interaction_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement interaction service**

```python
# src/cps/services/interaction_service.py
"""Track user interactions for behavior inference (spec Section 4.1 layer 3).

Records: button clicks, messages, search queries.
Queries: repeated search patterns → infer product interest.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import UserInteraction


class InteractionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        user_id: int,
        interaction_type: str,
        payload: str | None = None,
    ) -> None:
        interaction = UserInteraction(
            user_id=user_id,
            interaction_type=interaction_type,
            payload=payload,
        )
        self._session.add(interaction)
        await self._session.flush()

    async def get_repeated_searches(
        self,
        user_id: int,
        min_count: int = 3,
        days: int = 7,
    ) -> list[tuple[str, int]]:
        """Find search queries repeated >= min_count times within N days.

        Returns list of (query_text, count) tuples ordered by count desc.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            select(
                UserInteraction.payload,
                func.count().label("cnt"),
            )
            .where(
                UserInteraction.user_id == user_id,
                UserInteraction.interaction_type == "search",
                UserInteraction.payload.isnot(None),
                UserInteraction.created_at >= cutoff,
            )
            .group_by(UserInteraction.payload)
            .having(func.count() >= min_count)
            .order_by(func.count().desc())
        )
        return [(row[0], row[1]) for row in result.all()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_interaction_service.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/cps/services/interaction_service.py tests/unit/test_interaction_service.py
git commit -m "feat: add interaction tracking service with behavior pattern queries"
```

---

### Task 23: Price checker + crawl scheduler jobs

**Files:**
- Create: `src/cps/jobs/__init__.py`
- Create: `src/cps/jobs/price_checker.py`
- Create: `src/cps/jobs/crawl_scheduler.py`

- [ ] **Step 1: Implement price checker job**

Create `src/cps/jobs/__init__.py` (empty).

```python
# src/cps/jobs/price_checker.py
"""Periodic job: check monitored ASINs for price drops → notify users.

Runs every 5 minutes via JobQueue. For each product with active monitors:
1. Get latest price from price_summary
2. Compare against each monitor's target_price
3. If current <= target AND cooldown expired → send price alert
"""
import structlog
from telegram.ext import ContextTypes

from cps.db.models import PriceMonitor, PriceSummary, Product, TelegramUser
from cps.db.session import get_session
from cps.bot.keyboards import build_buy_keyboard, to_telegram_markup
from cps.bot.messages import MessageTemplates
from cps.services.affiliate import build_product_link
from cps.services.monitor_service import MonitorService
from cps.services.notification_service import NotificationService
from cps.services.price_service import format_price
from cps.services.user_service import UserService

from sqlalchemy import select, distinct
from telegram.error import Forbidden

log = structlog.get_logger()


async def price_checker_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called by JobQueue every 5 minutes."""
    settings = context.bot_data["settings"]
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        # Get all products with active monitors
        result = await session.execute(
            select(distinct(PriceMonitor.product_id)).where(
                PriceMonitor.is_active == True,  # noqa: E712
                PriceMonitor.target_price.isnot(None),
            )
        )
        product_ids = [row[0] for row in result.all()]

        for product_id in product_ids:
            try:
                await _check_product_monitors(
                    session, context.bot, product_id, settings
                )
            except Exception as exc:
                log.error("price_check_error", product_id=product_id, error=str(exc))

        await session.commit()

    log.info("price_checker_complete", products_checked=len(product_ids))


async def _check_product_monitors(session, bot, product_id, settings):
    """Check all monitors for a single product."""
    # Get current price
    ps_result = await session.execute(
        select(PriceSummary).where(
            PriceSummary.product_id == product_id,
            PriceSummary.price_type == "amazon",
        )
    )
    summary = ps_result.scalar_one_or_none()
    if summary is None or summary.current_price is None:
        return

    current_price = summary.current_price

    # Get product info
    product = await session.get(Product, product_id)
    if product is None:
        return

    # Get all active monitors with target below current
    mon_result = await session.execute(
        select(PriceMonitor).where(
            PriceMonitor.product_id == product_id,
            PriceMonitor.is_active == True,  # noqa: E712
            PriceMonitor.target_price >= current_price,
        )
    )
    monitors = list(mon_result.scalars().all())

    mon_svc = MonitorService(session)
    notification_svc = NotificationService(bot, session)

    for monitor in monitors:
        if MonitorService.is_cooldown_active(monitor.last_notified_at):
            continue

        # Get user
        user = await session.get(TelegramUser, monitor.user_id)
        if user is None or user.notification_state == "blocked":
            continue

        # Build alert message
        templates = MessageTemplates(user.language)
        is_all_time = current_price <= (summary.lowest_price or current_price)
        msg = templates.price_alert(
            title=product.title or product.asin,
            current=format_price(current_price),
            target=format_price(monitor.target_price),
            historical_low=format_price(summary.lowest_price or current_price),
            is_all_time=is_all_time,
        )

        buy_url = build_product_link(product.asin, settings.affiliate_tag)
        kb = to_telegram_markup(build_buy_keyboard(buy_url))

        try:
            await notification_svc.send(
                telegram_id=user.telegram_id,
                text=msg,
                notification_type="price_alert",
                reply_markup=kb,
                product_id=product_id,
                affiliate_tag=settings.affiliate_tag,
            )
            await mon_svc.mark_notified(monitor)
        except Forbidden:
            user_svc = UserService(session)
            await user_svc.mark_blocked(user)
            log.warning("user_blocked", telegram_id=user.telegram_id)
```

- [ ] **Step 2: Implement crawl scheduler job**

```python
# src/cps/jobs/crawl_scheduler.py
"""Periodic job: schedule re-crawls for monitored ASINs.

Runs every 5 minutes. Picks products whose crawl_task.next_crawl_at has passed
and resets them to pending for the pipeline to pick up.
"""
import structlog
from datetime import datetime, timezone

from telegram.ext import ContextTypes

from cps.db.models import CrawlTask
from cps.db.session import get_session

from sqlalchemy import select, update

log = structlog.get_logger()


async def crawl_scheduler_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called by JobQueue every 5 minutes."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        now = datetime.now(timezone.utc)

        # Find completed tasks whose next_crawl_at has passed
        result = await session.execute(
            select(CrawlTask).where(
                CrawlTask.status == "completed",
                CrawlTask.next_crawl_at <= now,
            ).limit(50)
        )
        tasks = list(result.scalars().all())

        for task in tasks:
            task.status = "pending"
            task.retry_count = 0
            task.error_message = None

        if tasks:
            await session.flush()
            await session.commit()

        log.info("crawl_scheduler_complete", rescheduled=len(tasks))
```

- [ ] **Step 3: Verify imports**

Run: `uv run python -c "from cps.jobs.price_checker import price_checker_job; from cps.jobs.crawl_scheduler import crawl_scheduler_job; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/cps/jobs/__init__.py src/cps/jobs/price_checker.py src/cps/jobs/crawl_scheduler.py
git commit -m "feat: add price checker and crawl scheduler background jobs"
```

---

### Task 24: Deal service + deal scanner + engagement manager

**Files:**
- Create: `src/cps/services/deal_service.py`
- Create: `src/cps/jobs/deal_scanner.py`
- Create: `src/cps/jobs/engagement.py`
- Create: `tests/unit/test_deal_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_deal_service.py
"""Tests for three-layer deal detection (spec Section 4.1)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from cps.services.deal_service import DealService, Deal


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_session):
    return DealService(mock_session)


class TestGlobalBestDeals:
    async def test_finds_products_at_historical_low(self, service, mock_session):
        # Product where current_price == lowest_price
        deal_row = MagicMock(
            product_id=1, current_price=16900, lowest_price=16900,
            product_title="AirPods Pro 2", product_asin="B08N5WRWNW",
            product_category="Electronics",
        )
        mock_result = MagicMock()
        mock_result.all.return_value = [deal_row]
        mock_session.execute = AsyncMock(return_value=mock_result)

        deals = await service.find_global_best(limit=10)
        assert len(deals) >= 1
        assert deals[0].asin == "B08N5WRWNW"


class TestDealFiltering:
    def test_filters_dismissed_categories(self):
        deals = [
            Deal(asin="B1", title="T1", category="Electronics", current=100, was=200),
            Deal(asin="B2", title="T2", category="Books", current=100, was=200),
        ]
        dismissed = {"Electronics"}
        filtered = DealService.filter_dismissed(deals, dismissed_categories=dismissed)
        assert len(filtered) == 1
        assert filtered[0].category == "Books"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_deal_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement deal service**

```python
# src/cps/services/deal_service.py
"""Three-layer deal detection (spec Section 4.1).

Layer 1: Related — products in same category as user's monitors at good prices
Layer 2: Global best — all-time lows across popular products
Layer 3: Behavior-inferred — products matching repeated search patterns
"""
from dataclasses import dataclass

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import PriceMonitor, PriceSummary, Product


@dataclass(frozen=True)
class Deal:
    asin: str
    title: str
    category: str | None
    current: int     # cents
    was: int         # highest price, cents


class DealService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_related(self, user_id: int, limit: int = 5) -> list[Deal]:
        """Layer 1: Find deals in categories the user monitors."""
        # Get user's monitored categories
        mon_result = await self._session.execute(
            select(Product.category).join(PriceMonitor).where(
                PriceMonitor.user_id == user_id,
                PriceMonitor.is_active == True,  # noqa: E712
                Product.category.isnot(None),
            ).distinct()
        )
        categories = [row[0] for row in mon_result.all()]
        if not categories:
            return []

        # Get monitored product IDs to exclude
        mon_pids = await self._session.execute(
            select(PriceMonitor.product_id).where(
                PriceMonitor.user_id == user_id,
            )
        )
        exclude_ids = {row[0] for row in mon_pids.all()}

        # Find products in same categories near historical low
        result = await self._session.execute(
            select(Product, PriceSummary).join(PriceSummary).where(
                Product.category.in_(categories),
                PriceSummary.price_type == "amazon",
                PriceSummary.current_price.isnot(None),
                PriceSummary.lowest_price.isnot(None),
                ~Product.id.in_(exclude_ids) if exclude_ids else True,
            ).limit(limit)
        )
        deals = []
        for product, ps in result.all():
            if ps.current_price <= ps.lowest_price * 1.1:  # within 10% of low
                deals.append(Deal(
                    asin=product.asin,
                    title=product.title or product.asin,
                    category=product.category,
                    current=ps.current_price,
                    was=ps.highest_price or ps.current_price,
                ))
        return deals[:limit]

    async def find_global_best(self, limit: int = 5) -> list[Deal]:
        """Layer 2: All-time lows across any product."""
        result = await self._session.execute(
            select(Product, PriceSummary).join(PriceSummary).where(
                PriceSummary.price_type == "amazon",
                PriceSummary.current_price.isnot(None),
                PriceSummary.lowest_price.isnot(None),
                PriceSummary.current_price <= PriceSummary.lowest_price,
            ).limit(limit)
        )
        return [
            Deal(
                asin=p.asin, title=p.title or p.asin,
                category=p.category,
                current=ps.current_price, was=ps.highest_price or ps.current_price,
            )
            for p, ps in result.all()
        ]

    async def find_by_search_pattern(
        self, search_query: str, limit: int = 3,
    ) -> list[Deal]:
        """Layer 3: Find products matching a search pattern at good prices."""
        pattern = f"%{search_query}%"
        result = await self._session.execute(
            select(Product, PriceSummary).join(PriceSummary).where(
                Product.title.ilike(pattern),
                PriceSummary.price_type == "amazon",
                PriceSummary.current_price.isnot(None),
                PriceSummary.lowest_price.isnot(None),
            ).limit(limit)
        )
        deals = []
        for p, ps in result.all():
            if ps.current_price <= ps.lowest_price * 1.15:  # within 15% of low
                deals.append(Deal(
                    asin=p.asin, title=p.title or p.asin,
                    category=p.category,
                    current=ps.current_price,
                    was=ps.highest_price or ps.current_price,
                ))
        return deals[:limit]

    @staticmethod
    def filter_dismissed(
        deals: list[Deal],
        dismissed_categories: set[str] | None = None,
        dismissed_asins: set[str] | None = None,
    ) -> list[Deal]:
        """Remove deals the user has dismissed."""
        result = []
        for d in deals:
            if dismissed_categories and d.category in dismissed_categories:
                continue
            if dismissed_asins and d.asin in dismissed_asins:
                continue
            result.append(d)
        return result
```

- [ ] **Step 4: Implement deal scanner and engagement jobs**

```python
# src/cps/jobs/deal_scanner.py
"""Periodic job: detect deals → push to eligible users.

Runs every hour. Respects adaptive push frequency and dismissals.
"""
import structlog
from telegram.ext import ContextTypes
from telegram.error import Forbidden

from cps.db.models import DealDismissal, TelegramUser
from cps.db.session import get_session
from cps.bot.keyboards import build_deal_push_keyboard, to_telegram_markup
from cps.bot.messages import MessageTemplates
from cps.services.affiliate import build_product_link
from cps.services.deal_service import DealService, Deal
from cps.services.notification_service import NotificationService
from cps.services.price_service import format_price
from cps.services.user_service import NotificationState, UserService

from sqlalchemy import select

log = structlog.get_logger()


async def deal_scanner_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called by JobQueue every hour."""
    settings = context.bot_data["settings"]
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        deal_svc = DealService(session)

        # Find global best deals
        global_deals = await deal_svc.find_global_best(limit=10)

        # Get eligible users (pushable states)
        pushable_states = [s.value for s in NotificationState if s.is_pushable]
        user_result = await session.execute(
            select(TelegramUser).where(
                TelegramUser.notification_state.in_(pushable_states)
            )
        )
        users = list(user_result.scalars().all())

        notification_svc = NotificationService(context.bot, session)
        sent_count = 0

        for user in users:
            try:
                await _push_deals_to_user(
                    session, notification_svc, deal_svc,
                    user, global_deals, settings,
                )
                sent_count += 1
            except Forbidden:
                user_svc = UserService(session)
                await user_svc.mark_blocked(user)
            except Exception as exc:
                log.error("deal_push_error", user_id=user.id, error=str(exc))

        await session.commit()
    log.info("deal_scanner_complete", users=len(users), sent=sent_count)


async def _push_deals_to_user(session, notification_svc, deal_svc, user, global_deals, settings):
    """Push best deal to a single user, respecting dismissals."""
    # Get user's dismissed categories and ASINs
    dismiss_result = await session.execute(
        select(DealDismissal).where(DealDismissal.user_id == user.id)
    )
    dismissals = list(dismiss_result.scalars().all())
    dismissed_cats = {d.dismissed_category for d in dismissals if d.dismissed_category}
    dismissed_asins = {d.dismissed_asin for d in dismissals if d.dismissed_asin}

    # Try all three layers
    all_deals: list[Deal] = []

    # Layer 1: Related
    related = await deal_svc.find_related(user.id, limit=3)
    all_deals.extend(related)

    # Layer 2: Global best
    all_deals.extend(global_deals)

    # Filter dismissed
    filtered = DealService.filter_dismissed(all_deals, dismissed_cats, dismissed_asins)
    if not filtered:
        return

    # Pick the best deal (first one)
    deal = filtered[0]
    templates = MessageTemplates(user.language)
    buy_url = build_product_link(deal.asin, settings.affiliate_tag)

    context_msg = f"Near historical low — only {round((deal.current / deal.was - 1) * 100)}% above."
    msg = templates.deal_push(
        title=deal.title,
        current=format_price(deal.current),
        original=format_price(deal.was),
        context=context_msg,
    )
    kb = to_telegram_markup(
        build_deal_push_keyboard(buy_url, deal.asin, deal.category)
    )

    await notification_svc.send(
        telegram_id=user.telegram_id,
        text=msg,
        notification_type="deal_push",
        reply_markup=kb,
        affiliate_tag=settings.affiliate_tag,
    )
```

```python
# src/cps/jobs/engagement.py
"""Periodic job: manage adaptive push frequency (spec Section 4.3).

Runs every hour. Checks last_interaction_at for each active user:
- 7 days idle → degrade to weekly
- 21 days idle → degrade to monthly
- 51 days idle → stop pushing

Also handles re-engagement prompt on user return.
"""
import structlog
from datetime import datetime, timedelta, timezone

from telegram.ext import ContextTypes
from telegram.error import Forbidden

from cps.db.models import TelegramUser
from cps.db.session import get_session
from cps.bot.keyboards import build_downgrade_keyboard, to_telegram_markup
from cps.bot.messages import MessageTemplates
from cps.services.notification_service import NotificationService
from cps.services.user_service import NotificationState, UserService

from sqlalchemy import select

log = structlog.get_logger()

_DEGRADE_TO_WEEKLY_DAYS = 7
_DEGRADE_TO_MONTHLY_DAYS = 21   # 7 + 14
_STOP_DAYS = 51                  # 21 + 30


async def engagement_manager_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called by JobQueue every hour."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        now = datetime.now(timezone.utc)
        user_svc = UserService(session)
        notification_svc = NotificationService(context.bot, session)

        # Find users to potentially downgrade
        result = await session.execute(
            select(TelegramUser).where(
                TelegramUser.notification_state == NotificationState.ACTIVE.value,
                TelegramUser.last_interaction_at.isnot(None),
                TelegramUser.last_interaction_at < now - timedelta(days=_DEGRADE_TO_WEEKLY_DAYS),
            )
        )
        users_to_degrade = list(result.scalars().all())

        for user in users_to_degrade:
            idle_days = (now - user.last_interaction_at).days if user.last_interaction_at else 0

            try:
                if idle_days >= _STOP_DAYS:
                    await user_svc.transition_state(user, NotificationState.STOPPED)
                    log.info("user_stopped", user_id=user.id, idle_days=idle_days)
                elif idle_days >= _DEGRADE_TO_MONTHLY_DAYS:
                    await user_svc.transition_state(user, NotificationState.DEGRADED_MONTHLY)
                    templates = MessageTemplates(user.language)
                    kb = to_telegram_markup(build_downgrade_keyboard("monthly"))
                    await notification_svc.send(
                        telegram_id=user.telegram_id,
                        text=templates.downgrade_notice("monthly"),
                        notification_type="system",
                        reply_markup=kb,
                    )
                elif idle_days >= _DEGRADE_TO_WEEKLY_DAYS:
                    await user_svc.transition_state(user, NotificationState.DEGRADED_WEEKLY)
                    templates = MessageTemplates(user.language)
                    kb = to_telegram_markup(build_downgrade_keyboard("weekly"))
                    await notification_svc.send(
                        telegram_id=user.telegram_id,
                        text=templates.downgrade_notice("weekly"),
                        notification_type="system",
                        reply_markup=kb,
                    )
            except Forbidden:
                await user_svc.mark_blocked(user)
            except Exception as exc:
                log.error("engagement_error", user_id=user.id, error=str(exc))

        await session.commit()
    log.info("engagement_check_complete", checked=len(users_to_degrade))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_deal_service.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/cps/services/deal_service.py src/cps/jobs/deal_scanner.py src/cps/jobs/engagement.py tests/unit/test_deal_service.py
git commit -m "feat: add deal service (3-layer detection) + deal scanner + engagement manager"
```

---

## Chunk 7: CLI Integration, Integration Tests, and Deployment

### Task 25: CLI bot command + job registration

**Files:**
- Modify: `src/cps/cli.py`
- Modify: `src/cps/bot/app.py`

- [ ] **Step 1: Register background jobs in app factory**

Add to `src/cps/bot/app.py`, inside `post_init` function, after the existing setup:

```python
    # Register periodic jobs
    from cps.jobs.price_checker import price_checker_job
    from cps.jobs.crawl_scheduler import crawl_scheduler_job
    from cps.jobs.deal_scanner import deal_scanner_job
    from cps.jobs.engagement import engagement_manager_job

    job_queue = application.job_queue
    job_queue.run_repeating(price_checker_job, interval=300, first=60)       # every 5 min
    job_queue.run_repeating(crawl_scheduler_job, interval=300, first=120)    # every 5 min
    job_queue.run_repeating(deal_scanner_job, interval=3600, first=300)      # every hour
    job_queue.run_repeating(engagement_manager_job, interval=3600, first=600)  # every hour
    log.info("jobs_registered")
```

- [ ] **Step 2: Add CLI bot command**

Add to `src/cps/cli.py`:

```python
bot_app = typer.Typer()
app.add_typer(bot_app, name="bot", help="Telegram bot operations")


@bot_app.command()
def run():
    """Start the Telegram bot (long-running process)."""
    import asyncio
    from cps.bot.app import create_bot_app
    from cps.config import get_settings

    settings = get_settings()
    if not settings.telegram_bot_token:
        typer.echo("Error: TELEGRAM_BOT_TOKEN not set", err=True)
        raise typer.Exit(1)

    application = create_bot_app(settings)
    application.run_polling()
```

- [ ] **Step 3: Verify CLI command is registered**

Run: `uv run cps bot --help`
Expected: Shows `run` subcommand

- [ ] **Step 4: Commit**

```bash
git add src/cps/bot/app.py src/cps/cli.py
git commit -m "feat: add CLI bot command and register all background jobs"
```

---

### Task 26: Integration tests (DB operations)

**Files:**
- Create: `tests/integration/test_user_repo.py`
- Create: `tests/integration/test_monitor_repo.py`

These tests require PostgreSQL running at `localhost:5433` (test database).

- [ ] **Step 1: Write user repository integration tests**

```python
# tests/integration/test_user_repo.py
"""Integration tests for user-layer DB operations."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import TelegramUser, UserInteraction, DealDismissal
from cps.services.user_service import NotificationState, UserService
from cps.services.interaction_service import InteractionService


class TestUserService:
    async def test_get_or_create_new_user(self, db_session: AsyncSession):
        svc = UserService(db_session)
        user = await svc.get_or_create(telegram_id=99999, username="inttest")
        assert user.id is not None
        assert user.telegram_id == 99999
        assert user.language == "en"
        assert user.notification_state == "active"

    async def test_get_or_create_existing(self, db_session: AsyncSession):
        svc = UserService(db_session)
        user1 = await svc.get_or_create(telegram_id=99998)
        user2 = await svc.get_or_create(telegram_id=99998)
        assert user1.id == user2.id

    async def test_state_transition(self, db_session: AsyncSession):
        svc = UserService(db_session)
        user = await svc.get_or_create(telegram_id=99997)
        assert await svc.transition_state(user, NotificationState.DEGRADED_WEEKLY) is True
        assert user.notification_state == "degraded_weekly"

    async def test_blocked_is_terminal(self, db_session: AsyncSession):
        svc = UserService(db_session)
        user = await svc.get_or_create(telegram_id=99996)
        await svc.mark_blocked(user)
        assert await svc.transition_state(user, NotificationState.ACTIVE) is False


class TestInteractionService:
    async def test_record_and_query(self, db_session: AsyncSession):
        user_svc = UserService(db_session)
        user = await user_svc.get_or_create(telegram_id=99995)

        int_svc = InteractionService(db_session)
        for _ in range(3):
            await int_svc.record(user.id, "search", "robot vacuum")
        await int_svc.record(user.id, "search", "airpods")

        patterns = await int_svc.get_repeated_searches(user.id, min_count=3, days=7)
        assert len(patterns) == 1
        assert patterns[0][0] == "robot vacuum"


class TestDealDismissal:
    async def test_dismiss_category(self, db_session: AsyncSession):
        user_svc = UserService(db_session)
        user = await user_svc.get_or_create(telegram_id=99994)

        dismissal = DealDismissal(user_id=user.id, dismissed_category="Electronics")
        db_session.add(dismissal)
        await db_session.flush()

        result = await db_session.execute(
            select(DealDismissal).where(DealDismissal.user_id == user.id)
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1
        assert rows[0].dismissed_category == "Electronics"
```

- [ ] **Step 2: Write monitor repository integration tests**

```python
# tests/integration/test_monitor_repo.py
"""Integration tests for monitor DB operations."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import Product, TelegramUser
from cps.services.monitor_service import MonitorService
from cps.services.user_service import UserService


class TestMonitorService:
    async def _setup_user_and_product(self, session: AsyncSession):
        user_svc = UserService(session)
        user = await user_svc.get_or_create(telegram_id=88888)
        product = Product(asin="B0TESTMON1")
        session.add(product)
        await session.flush()
        return user, product

    async def test_create_monitor(self, db_session: AsyncSession):
        user, product = await self._setup_user_and_product(db_session)
        svc = MonitorService(db_session)
        monitor = await svc.create_monitor(user.id, product.id, target_price=16900)
        assert monitor is not None
        assert monitor.target_price == 16900

    async def test_20_limit_enforcement(self, db_session: AsyncSession):
        user_svc = UserService(db_session)
        user = await user_svc.get_or_create(telegram_id=88887)
        svc = MonitorService(db_session)

        # Create 20 products + monitors
        for i in range(20):
            p = Product(asin=f"B0LIMIT{i:04d}")
            db_session.add(p)
            await db_session.flush()
            await svc.create_monitor(user.id, p.id)

        # 21st should fail
        extra = Product(asin="B0LIMITEXTR")
        db_session.add(extra)
        await db_session.flush()
        result = await svc.create_monitor(user.id, extra.id)
        assert result is None

    async def test_remove_monitor(self, db_session: AsyncSession):
        user, product = await self._setup_user_and_product(db_session)
        svc = MonitorService(db_session)
        await svc.create_monitor(user.id, product.id)
        assert await svc.remove_monitor(user.id, product.id) is True
        assert await svc.count_active(user.id) == 0

    async def test_duplicate_monitor_reactivates(self, db_session: AsyncSession):
        user, product = await self._setup_user_and_product(db_session)
        svc = MonitorService(db_session)
        m1 = await svc.create_monitor(user.id, product.id, target_price=100)
        await svc.remove_monitor(user.id, product.id)
        m2 = await svc.create_monitor(user.id, product.id, target_price=200)
        assert m2.is_active is True
        assert m2.target_price == 200
```

- [ ] **Step 3: Run integration tests**

Run: `uv run pytest tests/integration/test_user_repo.py tests/integration/test_monitor_repo.py -v`
Expected: All tests PASS (requires test PostgreSQL at localhost:5433)

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_user_repo.py tests/integration/test_monitor_repo.py
git commit -m "test: add integration tests for user and monitor DB operations"
```

---

### Task 27: Full test suite + coverage check + deployment config

**Files:**
- Modify: `pyproject.toml` (coverage omit for new bot modules)

- [ ] **Step 1: Update coverage config**

Add to `pyproject.toml` `[tool.coverage.report]` `omit` list:

```toml
    "src/cps/bot/app.py",
    "src/cps/bot/handlers/*.py",
    "src/cps/jobs/*.py",
```

(Handlers and jobs depend on Telegram runtime — unit test coverage comes from service-layer tests.)

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v --cov --cov-report=term-missing`
Expected: All tests PASS, coverage ≥ 80%

- [ ] **Step 3: Create environment variable documentation**

Add to project `.env.example` (or update existing):

```bash
# === Phase 1 (existing) ===
DATABASE_URL=postgresql+asyncpg://cps:password@localhost:5432/cps
CCC_BASE_URL=https://charts.camelcamelcamel.com/us
CCC_RATE_LIMIT=1.0
DATA_DIR=data
LOG_LEVEL=INFO
RESEND_API_KEY=
ALERT_EMAIL_TO=
ALERT_EMAIL_FROM=alerts@cps.local

# === Phase 2 (Telegram Bot) ===
TELEGRAM_BOT_TOKEN=          # from @BotFather
AFFILIATE_TAG=               # e.g., buypulse-20
DEMO_ASIN=B0D1XD1ZV3        # pre-seeded product for onboarding
ANTHROPIC_API_KEY=           # for Claude Haiku (NLP + language detection)
```

- [ ] **Step 4: Create systemd service file for VPS**

```ini
# deploy/buypulse-bot.service
[Unit]
Description=BuyPulse Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=cps
WorkingDirectory=/home/cps/cps
EnvironmentFile=/home/cps/cps/.env
ExecStart=/home/cps/.local/bin/uv run cps bot run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example deploy/buypulse-bot.service
git commit -m "chore: update coverage config, add env docs and systemd service file"
```

---

## Chunk 8: Review Fixes (Spec Gaps Identified During Review)

These tasks address spec requirements that were missing from the initial plan.

### Task 28: Language auto-detection on first message

**Spec Section 6**: "AI auto-detection: First message from user → detect language → set default"

**Files:**
- Modify: `src/cps/bot/handlers/start.py`
- Modify: `src/cps/bot/handlers/price_check.py`

- [ ] **Step 1: Use Telegram's `language_code` in /start handler**

In `start_command`, after `get_or_create`, detect language:

```python
        # Auto-detect language from Telegram client language
        tg_lang = (tg_user.language_code or "")[:2].lower()
        if tg_lang in ("es",) and user.language == "en":
            await user_svc.update_language(user, "es")
```

- [ ] **Step 2: AI-detect language on first NLP message**

In `handle_text_message`, after NLP classification, if user has no recorded interactions yet:

```python
        # Auto-detect language on first text message
        if user.last_interaction_at is None:
            ai_client = context.bot_data["ai_client"]
            detected = await ai_client.detect_language(text)
            if detected != user.language:
                await user_svc.update_language(user, detected)
```

- [ ] **Step 3: Commit**

```bash
git add src/cps/bot/handlers/start.py src/cps/bot/handlers/price_check.py
git commit -m "feat: add language auto-detection from Telegram client + first message AI detection"
```

---

### Task 29: On-demand crawl failure notification

**Spec Section 3.2/7.1**: "If crawl fails after all retries, notify user within 1 hour"

**Files:**
- Modify: `src/cps/db/models.py` (add `requested_by_user_id` to CrawlTask)
- Modify: `alembic/versions/002_user_layer.py` (add column)
- Create: `src/cps/jobs/crawl_failure_notifier.py`
- Modify: `src/cps/bot/handlers/price_check.py` (set requested_by when creating on-demand crawl)

- [ ] **Step 1: Add `requested_by_user_id` to CrawlTask**

Add to `CrawlTask` in `models.py`:

```python
    requested_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("telegram_users.id"), nullable=True
    )
```

Add to migration `002_user_layer.py`:

```python
    # Add requested_by_user_id to existing crawl_tasks table
    op.add_column("crawl_tasks", sa.Column(
        "requested_by_user_id", sa.BigInteger,
        sa.ForeignKey("telegram_users.id"), nullable=True,
    ))
```

- [ ] **Step 2: Set requested_by in on-demand crawl**

Modify `src/cps/services/crawl_service.py` `upsert_crawl_task` to accept `requested_by_user_id`:

```python
async def upsert_crawl_task(
    session: AsyncSession,
    product_id: int,
    priority: int = 1,
    requested_by_user_id: int | None = None,
) -> None:
    stmt = pg_insert(CrawlTask).values(
        product_id=product_id,
        priority=priority,
        status="pending",
        requested_by_user_id=requested_by_user_id,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["product_id"],
        set_={
            "status": "pending",
            "priority": priority,
            "retry_count": 0,
            "error_message": None,
            "requested_by_user_id": requested_by_user_id,
        },
    )
    await session.execute(stmt)
    await session.flush()
```

- [ ] **Step 3: Create crawl failure notifier job**

```python
# src/cps/jobs/crawl_failure_notifier.py
"""Periodic job: notify users when their on-demand crawl request fails.

Runs every 10 minutes. Checks for failed crawl tasks with a requesting user.
"""
import structlog
from telegram.ext import ContextTypes
from telegram.error import Forbidden

from cps.db.models import CrawlTask, Product, TelegramUser
from cps.db.session import get_session
from cps.bot.messages import MessageTemplates
from cps.services.notification_service import NotificationService
from cps.services.user_service import UserService

from sqlalchemy import select

log = structlog.get_logger()


async def crawl_failure_notifier_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check for failed on-demand crawls and notify requesting users."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        result = await session.execute(
            select(CrawlTask).where(
                CrawlTask.status == "failed",
                CrawlTask.requested_by_user_id.isnot(None),
            )
        )
        failed_tasks = list(result.scalars().all())

        notification_svc = NotificationService(context.bot, session)

        for task in failed_tasks:
            user = await session.get(TelegramUser, task.requested_by_user_id)
            product = await session.get(Product, task.product_id)
            if user is None or product is None:
                continue
            if user.notification_state == "blocked":
                continue

            templates = MessageTemplates(user.language)
            try:
                await notification_svc.send(
                    telegram_id=user.telegram_id,
                    text=templates.crawl_failed(product.asin),
                    notification_type="system",
                    user_id=user.id,
                )
            except Forbidden:
                user_svc = UserService(session)
                await user_svc.mark_blocked(user)

            # Clear requested_by so we don't notify again
            task.requested_by_user_id = None

        await session.commit()
```

Register in `post_init` in `app.py`:
```python
    from cps.jobs.crawl_failure_notifier import crawl_failure_notifier_job
    job_queue.run_repeating(crawl_failure_notifier_job, interval=600, first=180)  # every 10 min
```

- [ ] **Step 4: Commit**

```bash
git add src/cps/db/models.py alembic/versions/002_user_layer.py src/cps/services/crawl_service.py src/cps/jobs/crawl_failure_notifier.py src/cps/bot/app.py src/cps/bot/handlers/price_check.py
git commit -m "feat: add on-demand crawl failure notification within 1 hour"
```

---

### Task 30: Monitor expiry notification (30 days stale)

**Spec Section 3.2**: "If product is delisted or CCC data goes stale (no update in 30 days), notify"

**Files:**
- Modify: `src/cps/jobs/engagement.py` (add monitor expiry check)
- Modify: `src/cps/bot/keyboards.py` (add expiry keyboard)

- [ ] **Step 1: Add expiry keyboard**

Add to `keyboards.py`:

```python
def build_monitor_expiry_keyboard(asin: str) -> list[list[dict]]:
    return [[
        _btn("Remove", f"remove_monitor:{asin}"),
        _btn("Keep watching", f"keep_monitor:{asin}"),
    ]]
```

- [ ] **Step 2: Add expiry check to engagement manager**

Add to `engagement_manager_job` in `engagement.py`:

```python
        # Check for stale monitored products (30+ days without price update)
        from cps.db.models import PriceMonitor, PriceSummary
        stale_cutoff = now - timedelta(days=30)
        stale_result = await session.execute(
            select(PriceMonitor, Product, PriceSummary)
            .join(Product, PriceMonitor.product_id == Product.id)
            .outerjoin(PriceSummary, and_(
                PriceSummary.product_id == Product.id,
                PriceSummary.price_type == "amazon",
            ))
            .where(
                PriceMonitor.is_active == True,
                or_(
                    PriceSummary.updated_at < stale_cutoff,
                    PriceSummary.id.is_(None),
                ),
            )
        )
        for monitor, product, ps in stale_result.all():
            user = await session.get(TelegramUser, monitor.user_id)
            if user is None or user.notification_state == "blocked":
                continue
            templates = MessageTemplates(user.language)
            msg = f"{product.title or product.asin} monitoring paused — product appears unavailable."
            from cps.bot.keyboards import build_monitor_expiry_keyboard, to_telegram_markup
            kb = to_telegram_markup(build_monitor_expiry_keyboard(product.asin))
            try:
                await notification_svc.send(
                    telegram_id=user.telegram_id, text=msg,
                    notification_type="system", reply_markup=kb, user_id=user.id,
                )
            except Forbidden:
                await user_svc.mark_blocked(user)
```

- [ ] **Step 3: Add `keep_monitor` callback handler in callbacks.py**

```python
        elif data.startswith("keep_monitor:"):
            await query.message.reply_text("OK, keeping this monitor active.")
```

- [ ] **Step 4: Commit**

```bash
git add src/cps/jobs/engagement.py src/cps/bot/keyboards.py src/cps/bot/handlers/callbacks.py
git commit -m "feat: add monitor expiry notification for 30-day stale products"
```

---

### Task 31: Fix NotificationService.send + global send rate + wiring fixes

This task fixes several code correctness issues found during review.

**Files:**
- Modify: `src/cps/services/notification_service.py`
- Modify: `src/cps/bot/handlers/price_check.py`
- Modify: `src/cps/bot/handlers/callbacks.py`

- [ ] **Step 1: Fix NotificationService — accept user_id, add global rate limiter**

```python
# Updated notification_service.py
import asyncio
import structlog
from telegram import Bot, InlineKeyboardMarkup
from telegram.error import Forbidden
from sqlalchemy.ext.asyncio import AsyncSession
from cps.db.models import NotificationLog

log = structlog.get_logger()

# Global send rate: 30 msg/s (Telegram API limit)
_GLOBAL_SEND_SEMAPHORE = asyncio.Semaphore(30)


class NotificationService:
    def __init__(self, bot: Bot, session: AsyncSession) -> None:
        self._bot = bot
        self._session = session

    async def send(
        self,
        telegram_id: int,
        text: str,
        notification_type: str,
        user_id: int,
        reply_markup: InlineKeyboardMarkup | None = None,
        product_id: int | None = None,
        affiliate_tag: str | None = None,
    ) -> bool:
        async with _GLOBAL_SEND_SEMAPHORE:
            await self._bot.send_message(
                chat_id=telegram_id, text=text, reply_markup=reply_markup,
            )
        log_entry = NotificationLog(
            user_id=user_id,
            product_id=product_id,
            notification_type=notification_type,
            message_text=text[:1000],
            affiliate_tag=affiliate_tag,
        )
        self._session.add(log_entry)
        return True
```

- [ ] **Step 2: Wire rate limiter into handle_text_message**

Add at top of `handle_text_message` in `price_check.py`:

```python
    # Rate limit check
    rate_state = context.bot_data.setdefault("_rate_limit_state", {})
    import time
    result = check_rate_limit(rate_state, update.effective_user.id, time.time())
    if result != RateLimitResult.ALLOWED:
        templates = MessageTemplates("en")  # minimal response
        await update.message.reply_text(templates.rate_limited())
        return
```

- [ ] **Step 3: Add missing settings callback handlers**

Add to `callbacks.py` routing:

```python
        elif data.startswith("set_density:"):
            density = data.split(":")[1]
            user_svc = UserService(session)
            user = await user_svc.get_by_telegram_id(update.effective_user.id)
            if user:
                await user_svc.update_density(user, density)
                await query.message.reply_text(f"Density set to {density}.")
        elif data.startswith("set_lang:"):
            lang = data.split(":")[1]
            user_svc = UserService(session)
            user = await user_svc.get_by_telegram_id(update.effective_user.id)
            if user:
                await user_svc.update_language(user, lang)
                labels = {"en": "English", "es": "Español"}
                await query.message.reply_text(f"Language set to {labels.get(lang, lang)}.")
        elif data == "pause_deals":
            user_svc = UserService(session)
            user = await user_svc.get_by_telegram_id(update.effective_user.id)
            if user:
                await user_svc.transition_state(user, NotificationState.PAUSED_BY_USER)
                await query.message.reply_text("Deal alerts paused. Use /settings to resume.")
        elif data == "delete_data":
            # Delete all user data (CCPA compliance, spec Section 7.5)
            user_svc = UserService(session)
            user = await user_svc.get_by_telegram_id(update.effective_user.id)
            if user:
                await session.delete(user)  # CASCADE deletes related records
                await query.message.reply_text("All your data has been deleted. Send /start to begin fresh.")
```

- [ ] **Step 4: Fix density toggle — pass density as parameter, not mutation**

Update `_send_price_report` in `price_check.py` to accept optional `density_override`:

```python
async def _send_price_report(update_or_query, session, user, product, settings, density_override=None):
    ...
    density = Density(density_override) if density_override else Density(user.density_preference)
    ...
```

Update `_handle_density_toggle` to use the override:

```python
async def _handle_density_toggle(update, context, session, data, settings):
    parts = data.split(":")
    density = parts[1]
    asin = parts[2]
    ...
    await _send_price_report(update.callback_query.message, session, user, product, settings, density_override=density)
```

- [ ] **Step 5: Add [View details] button to /monitors**

In `monitors.py`, change the monitor item to include a details button:

```python
def build_monitor_item_keyboard(asin: str) -> list[list[dict]]:
    return [
        [_btn("View details", f"view_detail:{asin}")],
        [_btn("Remove", f"remove_monitor:{asin}")],
    ]
```

Add handler in `callbacks.py`:

```python
        elif data.startswith("view_detail:"):
            asin = data.split(":")[1]
            # Trigger price report for this ASIN
            result = await session.execute(select(Product).where(Product.asin == asin))
            product = result.scalar_one_or_none()
            if product:
                user_svc = UserService(session)
                user = await user_svc.get_by_telegram_id(update.effective_user.id)
                if user:
                    from cps.bot.handlers.price_check import _send_price_report
                    await _send_price_report(query.message, session, user, product, settings)
```

- [ ] **Step 6: Commit**

```bash
git add src/cps/services/notification_service.py src/cps/bot/handlers/price_check.py src/cps/bot/handlers/callbacks.py src/cps/bot/handlers/monitors.py
git commit -m "fix: notification user_id, global rate limit, settings callbacks, density toggle, monitor details"
```

---

### Task 32: Historical all-time low bypasses push frequency limits

**Spec Section 4.3**: "Historical all-time low → push immediately | Bypasses frequency limits"

**Files:**
- Modify: `src/cps/jobs/deal_scanner.py`
- Modify: `src/cps/jobs/price_checker.py`

- [ ] **Step 1: Add all-time-low bypass in deal_scanner**

In `deal_scanner_job`, expand user query to include all non-blocked users when deal is all-time low:

```python
        # Separate all-time lows (bypass frequency limits)
        atl_deals = [d for d in global_deals if d.current <= d.was * 0.05 + d.current]  # current ≈ lowest
        regular_deals = [d for d in global_deals if d not in atl_deals]

        # For ATL deals: push to ALL non-blocked users (bypass frequency)
        if atl_deals:
            all_users_result = await session.execute(
                select(TelegramUser).where(
                    TelegramUser.notification_state != "blocked"
                )
            )
            all_users = list(all_users_result.scalars().all())
            for user in all_users:
                # ... push ATL deal (same logic as _push_deals_to_user but bypasses state check)
```

- [ ] **Step 2: Add all-time-low bypass in price_checker**

In `_check_product_monitors`, after cooldown check:

```python
        # All-time low bypasses cooldown
        is_all_time_low = current_price <= (summary.lowest_price or current_price)
        if MonitorService.is_cooldown_active(monitor.last_notified_at) and not is_all_time_low:
            continue
```

- [ ] **Step 3: Commit**

```bash
git add src/cps/jobs/deal_scanner.py src/cps/jobs/price_checker.py
git commit -m "feat: historical all-time low bypasses push frequency and cooldown limits"
```

---

## Execution Notes

### Dependency Order

Tasks MUST be executed in order within each chunk. Chunks 1-3 must complete before Chunks 4-7. Within Chunks 4-7, the dependency graph is:

```
Chunk 4 (messages, keyboards) → Chunk 5 (handlers use messages + keyboards)
Chunk 3 (services) → Chunk 6 (jobs use services)
Chunk 5 + Chunk 6 → Chunk 7 (integration tests use everything)
```

### Parallel Execution Opportunities

These task groups can run in parallel if using subagent-driven development:
- **Group A**: Tasks 5, 6, 7 (independent services)
- **Group B**: Tasks 13, 14 (presentation layer)
- **Group C**: Tasks 20, 21, 22 (rate limiter + notification + interaction)

### Pre-seeding Demo Product

Before first bot run, ensure the demo ASIN (`B0D1XD1ZV3`) is in the database with price data:

```bash
uv run cps seed add B0D1XD1ZV3
uv run cps crawl run --limit 1
```

### Integration Test Prerequisites

Integration tests require:
- PostgreSQL running at `localhost:5433` (test database)
- Test DB user: `cps_test` / `cps_test_password`
- Migration: `uv run alembic upgrade head` (on test DB)
