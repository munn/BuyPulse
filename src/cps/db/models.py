"""SQLAlchemy ORM models for CPS — core + user-layer tables."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    REAL,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asin: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    extraction_runs: Mapped[list["ExtractionRun"]] = relationship(
        back_populates="product"
    )
    price_summaries: Mapped[list["PriceSummary"]] = relationship(
        back_populates="product"
    )
    crawl_task: Mapped["CrawlTask | None"] = relationship(back_populates="product")
    monitors: Mapped[list["PriceMonitor"]] = relationship(back_populates="product")

    __table_args__ = (Index("idx_products_category", "category"),)


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    chart_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    points_extracted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(REAL, nullable=True)
    validation_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="extraction_runs")

    __table_args__ = (
        Index("idx_er_product", "product_id"),
        Index("idx_er_status", "status"),
    )


class PriceHistory(Base):
    """Core price time series table — partitioned by year on recorded_date.

    Partitions are created in the Alembic migration, not here.
    SQLAlchemy maps to the parent table; PostgreSQL routes rows to partitions.
    """

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    price_type: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ccc_chart"
    )
    extraction_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("extraction_runs.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Composite PK required for PostgreSQL partitioning
        {"postgresql_partition_by": "RANGE (recorded_date)"},
    )
    __mapper_args__ = {"primary_key": [id, recorded_date]}


class PriceSummary(Base):
    __tablename__ = "price_summary"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    price_type: Mapped[str] = mapped_column(String(20), nullable=False)
    lowest_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lowest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    highest_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    highest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="ccc_legend"
    )
    extraction_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("extraction_runs.id"), nullable=True
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
    product: Mapped["Product"] = relationship(back_populates="price_summaries")

    __table_args__ = (
        Index(
            "uq_price_summary_product_type",
            "product_id",
            "price_type",
            unique=True,
        ),
    )


class DailySnapshot(Base):
    """Phase 2 placeholder — partitioned by year on snapshot_date."""

    __tablename__ = "daily_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="creators_api"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        {"postgresql_partition_by": "RANGE (snapshot_date)"},
    )
    __mapper_args__ = {"primary_key": [id, snapshot_date]}


class CrawlTask(Base):
    __tablename__ = "crawl_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id"), nullable=False, unique=True
    )
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=5)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_crawl_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_crawls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
    product: Mapped["Product"] = relationship(back_populates="crawl_task")

    __table_args__ = (
        Index("idx_ct_status_priority", "status", "priority", "scheduled_at"),
        Index(
            "idx_ct_next_crawl",
            "next_crawl_at",
            postgresql_where="status = 'completed'",
        ),
    )


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
