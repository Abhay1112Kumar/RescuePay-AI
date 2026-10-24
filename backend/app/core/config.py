"""Application configuration settings using pydantic-settings.

Centralizes all environment variables with typed validation, secure secret handling,
and safe development defaults for Phase 1 of RescuePay-AI.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory for backend (anchor path for .env file resolution)
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """Application settings schema and environment variable loader."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core Application Settings
    APP_NAME: str = "RescuePay-AI"
    APP_ENV: Literal["development", "testing", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"

    # PayPal Configuration (Sandbox initial environment)
    PAYPAL_MODE: Literal["sandbox", "live"] = "sandbox"
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_BASE_URL: str = "https://api-m.sandbox.paypal.com"

    def __repr__(self) -> str:
        """Sanitized string representation ensuring secrets are never leaked."""
        secret_masked = "******" if self.PAYPAL_CLIENT_SECRET else ""
        return (
            f"Settings(APP_NAME={self.APP_NAME!r}, APP_ENV={self.APP_ENV!r}, "
            f"DEBUG={self.DEBUG!r}, PAYPAL_MODE={self.PAYPAL_MODE!r}, "
            f"PAYPAL_CLIENT_ID={self.PAYPAL_CLIENT_ID!r}, "
            f"PAYPAL_CLIENT_SECRET={secret_masked!r}, "
            f"PAYPAL_BASE_URL={self.PAYPAL_BASE_URL!r})"
        )

    def __str__(self) -> str:
        """Sanitized string representation."""
        return self.__repr__()


@lru_cache
def get_settings() -> Settings:
    """Reusable dependency / accessor returning a cached Settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear cached settings instance to ensure isolated test execution."""
    get_settings.cache_clear()
