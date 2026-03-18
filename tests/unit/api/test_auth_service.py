"""Tests for auth service — password hashing and session management."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from cps.api.auth import (
    create_session, delete_session, hash_password, validate_session, verify_password,
)


class TestPasswordHashing:
    def test_hash_password_returns_bcrypt_hash(self):
        hashed = hash_password("securepassword1")
        assert hashed.startswith("$2b$")

    def test_verify_correct_password(self):
        hashed = hash_password("test_password_123")
        assert verify_password("test_password_123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("test_password_123")
        assert verify_password("wrong_password", hashed) is False

    def test_hash_is_unique_per_call(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2


class TestCreateSession:
    async def test_creates_session_row(self):
        mock_session = AsyncMock()
        token = await create_session(mock_session, 42, 7)
        assert isinstance(token, str)
        assert len(token) >= 40
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()


class TestValidateSession:
    async def test_valid_session_returns_user(self):
        mock_session = AsyncMock()
        mock_admin_session = MagicMock()
        mock_admin_session.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        mock_admin_session.user_id = 42

        mock_user = MagicMock()
        mock_user.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_admin_session
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.side_effect = [mock_result, mock_user_result]

        user = await validate_session(mock_session, "valid_token")
        assert user is mock_user

    async def test_expired_session_returns_none(self):
        mock_session = AsyncMock()
        mock_admin_session = MagicMock()
        mock_admin_session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_admin_session
        mock_session.execute.return_value = mock_result

        user = await validate_session(mock_session, "expired_token")
        assert user is None

    async def test_missing_session_returns_none(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        user = await validate_session(mock_session, "nonexistent_token")
        assert user is None


class TestDeleteSession:
    async def test_deletes_by_token(self):
        mock_session = AsyncMock()
        await delete_session(mock_session, "some_token")
        mock_session.execute.assert_awaited_once()
