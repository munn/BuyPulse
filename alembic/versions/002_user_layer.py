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
