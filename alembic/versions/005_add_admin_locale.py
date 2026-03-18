"""Add locale column to admin_users."""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("admin_users", sa.Column("locale", sa.String(10), nullable=False, server_default="zh-CN"))
    op.create_check_constraint(
        "ck_admin_users_locale",
        "admin_users",
        "locale IN ('zh-CN', 'en-US', 'es-ES')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_admin_users_locale", "admin_users", type_="check")
    op.drop_column("admin_users", "locale")
