"""T010: Unit tests for cps.config — Settings and get_settings.

These tests verify:
- Required environment variables cause validation errors when missing
- Default values are applied correctly
- Type coercion from string env vars to typed fields
- get_settings() returns a valid Settings instance
"""

import pytest
from pydantic import ValidationError

from cps.config import Settings, get_settings


class TestSettingsRequiredVars:
    """Settings must fail fast when required vars are missing."""

    def test_loads_successfully_with_required_vars(self, monkeypatch):
        """All required vars present -> config loads without error."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")

        settings = Settings()  # type: ignore[call-arg]

        assert settings.database_url == "postgresql+asyncpg://u:p@localhost/db"

    def test_missing_database_url_raises_validation_error(self, monkeypatch):
        """Missing DATABASE_URL -> ValidationError at startup."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        # Also remove .env to avoid loading from file
        monkeypatch.setitem(Settings.model_config, "env_file", None)

        with pytest.raises(ValidationError) as exc_info:
            Settings()  # type: ignore[call-arg]

        # Ensure the error mentions the missing field
        assert "database_url" in str(exc_info.value).lower()


class TestSettingsDefaults:
    """Default values must be applied when env vars are not set."""

    @pytest.fixture(autouse=True)
    def _set_required_vars(self, monkeypatch):
        """Provide required vars and disable .env file to test code defaults."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
        monkeypatch.delenv("LOG_FORMAT", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("DATA_DIR", raising=False)
        monkeypatch.delenv("CCC_RATE_LIMIT", raising=False)
        monkeypatch.delenv("CCC_RETRY_MAX", raising=False)
        monkeypatch.setitem(Settings.model_config, "env_file", None)

    def test_default_ccc_rate_limit(self):
        settings = Settings()  # type: ignore[call-arg]
        assert settings.ccc_rate_limit == 1.0

    def test_default_ccc_retry_max(self):
        settings = Settings()  # type: ignore[call-arg]
        assert settings.ccc_retry_max == 3

    def test_default_log_level(self):
        settings = Settings()  # type: ignore[call-arg]
        assert settings.log_level == "INFO"

    def test_default_log_format(self):
        settings = Settings()  # type: ignore[call-arg]
        assert settings.log_format == "json"

    def test_default_data_dir(self):
        from pathlib import Path

        settings = Settings()  # type: ignore[call-arg]
        assert settings.data_dir == Path("data")


class TestSettingsTypeCoercion:
    """Env vars are strings; pydantic-settings must coerce to correct types."""

    @pytest.fixture(autouse=True)
    def _set_required_vars(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")

    def test_ccc_rate_limit_string_to_float(self, monkeypatch):
        """String '2.5' in env -> float 2.5 in settings."""
        monkeypatch.setenv("CCC_RATE_LIMIT", "2.5")

        settings = Settings()  # type: ignore[call-arg]

        assert settings.ccc_rate_limit == 2.5
        assert isinstance(settings.ccc_rate_limit, float)

    def test_ccc_retry_max_string_to_int(self, monkeypatch):
        """String '5' in env -> int 5 in settings."""
        monkeypatch.setenv("CCC_RETRY_MAX", "5")

        settings = Settings()  # type: ignore[call-arg]

        assert settings.ccc_retry_max == 5
        assert isinstance(settings.ccc_retry_max, int)

    def test_data_dir_string_to_path(self, monkeypatch):
        """String '/tmp/charts' in env -> Path('/tmp/charts') in settings."""
        from pathlib import Path

        monkeypatch.setenv("DATA_DIR", "/tmp/charts")

        settings = Settings()  # type: ignore[call-arg]

        assert settings.data_dir == Path("/tmp/charts")
        assert isinstance(settings.data_dir, Path)


class TestBotSettings:
    """Bot-related settings fields and defaults."""

    def test_bot_settings_fields(self):
        """Verify new bot-related fields exist on Settings."""
        field_names = set(Settings.model_fields.keys())
        assert field_names >= {
            "telegram_bot_token", "affiliate_tag",
            "siliconflow_api_key", "siliconflow_base_url", "demo_product_id",
        }

    def test_bot_defaults(self):
        """Verify sensible defaults for bot settings."""
        fields = Settings.model_fields
        assert fields["affiliate_tag"].default == ""
        assert fields["demo_product_id"].default == "B0D1XD1ZV3"


class TestGetSettings:
    """get_settings() factory function."""

    def test_returns_settings_instance(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")

        result = get_settings()

        assert isinstance(result, Settings)

    def test_returns_fresh_instance_each_call(self, monkeypatch):
        """Each call creates a new Settings (no caching)."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")

        s1 = get_settings()
        s2 = get_settings()

        assert s1 is not s2
