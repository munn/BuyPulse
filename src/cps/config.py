"""Application configuration via environment variables."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """CPS application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = Field(
        description="PostgreSQL connection string for the main database",
    )
    test_database_url: str = Field(
        default="postgresql+asyncpg://cps_test:cps_test_password@localhost:5433/cps_test",
        description="PostgreSQL connection string for the test database",
    )

    # CCC chart download
    ccc_base_url: str = Field(
        default="https://charts.camelcamelcamel.com/us",
        description="Base URL for CCC chart images",
    )
    ccc_rate_limit: float = Field(
        default=1.0,
        description="Max requests per second to CCC",
    )
    ccc_retry_max: int = Field(
        default=3,
        description="Max retry attempts for failed downloads",
    )
    ccc_backoff_base: float = Field(
        default=2.0,
        description="Exponential backoff base in seconds",
    )
    ccc_cooldown_secs: float = Field(
        default=60.0,
        description="Cooldown duration after HTTP 429 in seconds",
    )

    # Alerts (Resend)
    resend_api_key: str = Field(
        default="",
        description="Resend API key for email alerts",
    )
    alert_email_to: str = Field(
        default="",
        description="Recipient email for alerts",
    )
    alert_email_from: str = Field(
        default="alerts@cps.local",
        description="Sender email for alerts",
    )

    # Storage
    data_dir: Path = Field(
        default=Path("data"),
        description="Root directory for chart PNGs and other data files",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Log level (DEBUG, INFO, WARNING, ERROR)",
    )
    log_format: str = Field(
        default="json",
        description="Log format: 'json' for production, 'console' for dev",
    )


def get_settings() -> Settings:
    """Create and return validated settings from environment."""
    return Settings()  # type: ignore[call-arg]
