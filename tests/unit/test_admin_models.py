"""Tests for admin ORM model definitions."""

from cps.db.models import AdminSession, AdminUser, AuditLog, ImportJob, WorkerHeartbeat


class TestAdminUserModel:
    def test_tablename(self):
        assert AdminUser.__tablename__ == "admin_users"

    def test_has_required_columns(self):
        col_names = {c.name for c in AdminUser.__table__.columns}
        expected = {"id", "username", "password_hash", "role", "is_active", "created_at", "updated_at"}
        assert expected.issubset(col_names)

    def test_username_unique(self):
        username_col = AdminUser.__table__.c.username
        assert username_col.unique is True


class TestAdminSessionModel:
    def test_tablename(self):
        assert AdminSession.__tablename__ == "admin_sessions"

    def test_has_required_columns(self):
        col_names = {c.name for c in AdminSession.__table__.columns}
        expected = {"id", "user_id", "session_token", "expires_at", "created_at"}
        assert expected.issubset(col_names)

    def test_session_token_unique(self):
        token_col = AdminSession.__table__.c.session_token
        assert token_col.unique is True


class TestWorkerHeartbeatModel:
    def test_tablename(self):
        assert WorkerHeartbeat.__tablename__ == "worker_heartbeats"

    def test_has_required_columns(self):
        col_names = {c.name for c in WorkerHeartbeat.__table__.columns}
        expected = {
            "id", "worker_id", "platform", "status", "current_task_id",
            "tasks_completed", "last_heartbeat", "started_at",
        }
        assert expected.issubset(col_names)

    def test_worker_id_unique(self):
        wid_col = WorkerHeartbeat.__table__.c.worker_id
        assert wid_col.unique is True


class TestImportJobModel:
    def test_tablename(self):
        assert ImportJob.__tablename__ == "import_jobs"

    def test_has_required_columns(self):
        col_names = {c.name for c in ImportJob.__table__.columns}
        expected = {
            "id", "filename", "status", "total", "processed",
            "added", "skipped", "error_message", "created_by",
            "created_at", "completed_at",
        }
        assert expected.issubset(col_names)


class TestAuditLogModel:
    def test_tablename(self):
        assert AuditLog.__tablename__ == "audit_log"

    def test_has_required_columns(self):
        col_names = {c.name for c in AuditLog.__table__.columns}
        expected = {
            "id", "user_id", "action", "resource_type",
            "resource_id", "details", "ip_address", "created_at",
        }
        assert expected.issubset(col_names)
