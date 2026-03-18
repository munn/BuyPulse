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
    op.drop_constraint("products_asin_key", "products", type_="unique")
    op.alter_column("products", "asin", new_column_name="platform_id")
    op.alter_column(
        "products", "platform_id",
        type_=sa.String(30), existing_type=sa.String(10),
        existing_nullable=False,
    )
    op.add_column("products", sa.Column(
        "platform", sa.String(30), nullable=False, server_default="amazon",
    ))
    op.add_column("products", sa.Column("url", sa.Text, nullable=True))
    op.add_column("products", sa.Column(
        "is_active", sa.Boolean, nullable=False, server_default="true",
    ))
    op.create_unique_constraint(
        "uq_platform_product", "products", ["platform", "platform_id"],
    )
    op.create_check_constraint(
        "ck_products_platform_valid", "products",
        "platform IN ('amazon')",
    )
    op.create_check_constraint(
        "ck_products_url_scheme", "products",
        "url IS NULL OR url ~ '^https://'",
    )
    op.create_index("idx_products_platform_active", "products", ["platform", "is_active"])

    # --- extraction_runs → fetch_runs ---
    op.rename_table("extraction_runs", "fetch_runs")
    op.alter_column(
        "fetch_runs", "chart_path",
        existing_type=sa.String(500), nullable=True,
    )
    op.add_column("fetch_runs", sa.Column(
        "platform", sa.String(30), nullable=False, server_default="amazon",
    ))
    op.create_check_constraint(
        "ck_fetch_runs_platform_valid", "fetch_runs",
        "platform IN ('amazon')",
    )
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
    # Safety guards
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM products WHERE LENGTH(platform_id) > 10) THEN
                RAISE EXCEPTION 'Downgrade blocked: platform_id values exceed VARCHAR(10).';
            END IF;
            IF EXISTS (SELECT 1 FROM deal_dismissals WHERE LENGTH(dismissed_platform_id) > 10) THEN
                RAISE EXCEPTION 'Downgrade blocked: dismissed_platform_id values exceed VARCHAR(10).';
            END IF;
            IF EXISTS (SELECT 1 FROM fetch_runs WHERE chart_path IS NULL) THEN
                RAISE EXCEPTION 'Downgrade blocked: fetch_runs has NULL chart_path rows.';
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
