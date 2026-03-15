"""Initial schema — 6 tables with partitioning.

Revision ID: 001
Revises:
Create Date: 2026-03-14
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 1. products ---
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("asin", sa.String(10), nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_products_category", "products", ["category"])

    # --- 2. extraction_runs ---
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "product_id",
            sa.BigInteger,
            sa.ForeignKey("products.id"),
            nullable=False,
        ),
        sa.Column("chart_path", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("points_extracted", sa.Integer, nullable=True),
        sa.Column("ocr_confidence", sa.REAL, nullable=True),
        sa.Column("validation_passed", sa.Boolean, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_er_product", "extraction_runs", ["product_id"])
    op.create_index("idx_er_status", "extraction_runs", ["status"])

    # --- 3. price_history (partitioned parent) ---
    op.execute("""
        CREATE TABLE price_history (
            id BIGSERIAL,
            product_id BIGINT NOT NULL REFERENCES products(id),
            price_type VARCHAR(20) NOT NULL,
            recorded_date DATE NOT NULL,
            price_cents INTEGER NOT NULL,
            source VARCHAR(20) NOT NULL DEFAULT 'ccc_chart',
            extraction_id BIGINT REFERENCES extraction_runs(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, recorded_date)
        ) PARTITION BY RANGE (recorded_date)
    """)
    op.create_index(
        "idx_ph_product_date", "price_history", ["product_id", "recorded_date"]
    )
    op.create_index(
        "idx_ph_product_type", "price_history", ["product_id", "price_type"]
    )

    # Create yearly partitions 2020-2026
    for year in range(2020, 2027):
        partition = f"price_history_{year}"
        op.execute(f"""
            CREATE TABLE {partition} PARTITION OF price_history
            FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01')
        """)
        # Per-partition unique constraint for dedup
        op.execute(f"""
            ALTER TABLE {partition}
            ADD CONSTRAINT uq_{partition}_dedup
            UNIQUE (product_id, price_type, recorded_date)
        """)

    # --- 4. price_summary ---
    op.create_table(
        "price_summary",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "product_id",
            sa.BigInteger,
            sa.ForeignKey("products.id"),
            nullable=False,
        ),
        sa.Column("price_type", sa.String(20), nullable=False),
        sa.Column("lowest_price", sa.Integer, nullable=True),
        sa.Column("lowest_date", sa.Date, nullable=True),
        sa.Column("highest_price", sa.Integer, nullable=True),
        sa.Column("highest_date", sa.Date, nullable=True),
        sa.Column("current_price", sa.Integer, nullable=True),
        sa.Column("current_date", sa.Date, nullable=True),
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default="ccc_legend",
        ),
        sa.Column(
            "extraction_id",
            sa.BigInteger,
            sa.ForeignKey("extraction_runs.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("product_id", "price_type", name="uq_price_summary_product_type"),
    )

    # --- 5. daily_snapshots (partitioned parent, Phase 2 placeholder) ---
    op.execute("""
        CREATE TABLE daily_snapshots (
            id BIGSERIAL,
            product_id BIGINT NOT NULL REFERENCES products(id),
            snapshot_date DATE NOT NULL,
            price_cents INTEGER NOT NULL,
            source VARCHAR(20) NOT NULL DEFAULT 'creators_api',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, snapshot_date)
        ) PARTITION BY RANGE (snapshot_date)
    """)
    op.create_index(
        "idx_ds_product_date", "daily_snapshots", ["product_id", "snapshot_date"]
    )

    # Create 2026 partition
    op.execute("""
        CREATE TABLE daily_snapshots_2026 PARTITION OF daily_snapshots
        FOR VALUES FROM ('2026-01-01') TO ('2027-01-01')
    """)

    # --- 6. crawl_tasks ---
    op.create_table(
        "crawl_tasks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "product_id",
            sa.BigInteger,
            sa.ForeignKey("products.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("priority", sa.SmallInteger, nullable=False, server_default="5"),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="'pending'"
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("max_retries", sa.SmallInteger, nullable=False, server_default="3"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("next_crawl_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_crawls", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_ct_status_priority",
        "crawl_tasks",
        ["status", "priority", "scheduled_at"],
    )
    op.execute("""
        CREATE INDEX idx_ct_next_crawl ON crawl_tasks (next_crawl_at)
        WHERE status = 'completed'
    """)


def downgrade() -> None:
    op.drop_table("crawl_tasks")
    op.execute("DROP TABLE daily_snapshots_2026")
    op.execute("DROP TABLE daily_snapshots")
    for year in range(2020, 2027):
        op.execute(f"DROP TABLE price_history_{year}")
    op.execute("DROP TABLE price_history")
    op.drop_table("price_summary")
    op.drop_table("extraction_runs")
    op.drop_table("products")
