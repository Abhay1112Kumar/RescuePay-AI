"""Application configuration settings using pydantic-settings.

Centralizes all environment variables with typed validation, secure secret handling,
and safe development defaults for RescuePay-AI.
"""

from decimal import Decimal
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
    LOG_LEVEL: str = "INFO"

    # PayPal Configuration (Sandbox initial environment)
    PAYPAL_MODE: Literal["sandbox", "live"] = "sandbox"
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_BASE_URL: str = "https://api-m.sandbox.paypal.com"
    PAYPAL_TIMEOUT_SECONDS: float = 15.0
    # Buyer is redirected here by PayPal after approving or cancelling checkout.
    PAYPAL_RETURN_URL: str = "http://localhost:5173/payment/return"
    PAYPAL_CANCEL_URL: str = "http://localhost:5173/payment/cancel"

    # Payment business rules (backend-enforced; never trust client-side limits)
    PAYMENT_ALLOWED_CURRENCIES: str = "USD"
    PAYMENT_MAX_AMOUNT: Decimal = Decimal("10000.00")

    @property
    def paypal_configured(self) -> bool:
        """True when both PayPal credentials are present."""
        return bool(self.PAYPAL_CLIENT_ID and self.PAYPAL_CLIENT_SECRET)

    @property
    def allowed_currencies(self) -> frozenset[str]:
        """Parsed, upper-cased set of ISO 4217 currency codes accepted for orders."""
        return frozenset(
            code.strip().upper()
            for code in self.PAYMENT_ALLOWED_CURRENCIES.split(",")
            if code.strip()
        )

    def __repr__(self) -> str:
        """Sanitized string representation ensuring secrets are never leaked."""
        secret_masked = "******" if self.PAYPAL_CLIENT_SECRET else ""
        return (
            f"Settings(APP_NAME={self.APP_NAME!r}, APP_ENV={self.APP_ENV!r}, "
            f"DEBUG={self.DEBUG!r}, PAYPAL_MODE={self.PAYPAL_MODE!r}, "
            f"PAYPAL_CLIENT_ID={self.PAYPAL_CLIENT_ID!r}, "
            f"PAYPAL_CLIENT_SECRET={secret_masked!r}, "
            f"PAYPAL_BASE_URL={self.PAYPAL_BASE_URL!r}, "
            f"PAYMENT_ALLOWED_CURRENCIES={self.PAYMENT_ALLOWED_CURRENCIES!r}, "
            f"PAYMENT_MAX_AMOUNT={str(self.PAYMENT_MAX_AMOUNT)!r})"
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
