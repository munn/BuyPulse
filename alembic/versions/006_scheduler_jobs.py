"""scheduler_jobs table + seed row.

Revision ID: 006
Revises: 005
Create Date: 2026-03-18
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduler_jobs",
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), server_default="offline", nullable=False),
        sa.Column("interval_s", sa.Integer(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_result", sa.Text(), nullable=True),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.execute(
        "INSERT INTO scheduler_jobs (name, status, interval_s) "
        "VALUES ('crawl_scheduler', 'offline', 300)"
    )


def downgrade() -> None:
    op.drop_table("scheduler_jobs")
