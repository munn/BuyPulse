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
        col = TelegramUser.__table__.c.monitor_limit
        assert col.default.arg == 20  # Column INSERT default


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
            "id", "user_id", "dismissed_category", "dismissed_platform_id", "created_at",
        }

    def test_check_constraint_exists(self):
        check_constraints = [
            c for c in DealDismissal.__table__.constraints
            if type(c).__name__ == "CheckConstraint"
        ]
        assert len(check_constraints) >= 1
