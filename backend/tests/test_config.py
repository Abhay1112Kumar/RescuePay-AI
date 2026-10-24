"""Tests for application settings and environment configuration."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, clear_settings_cache, get_settings
from app.main import app


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Ensure cached settings are cleared before and after each test for isolation."""
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_default_application_settings() -> None:
    """Verify default application settings match expected values without .env overrides."""
    settings = Settings(_env_file=None)
    assert settings.APP_NAME == "RescuePay-AI"
    assert settings.APP_ENV == "development"
    assert settings.DEBUG is False
    assert settings.API_V1_STR == "/api/v1"


def test_sandbox_configuration_defaults() -> None:
    """Verify PayPal sandbox defaults."""
    settings = Settings(_env_file=None)
    assert settings.PAYPAL_MODE == "sandbox"
    assert settings.PAYPAL_BASE_URL == "https://api-m.sandbox.paypal.com"
    assert settings.PAYPAL_CLIENT_ID == ""
    assert settings.PAYPAL_CLIENT_SECRET == ""


def test_environment_variable_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify system environment variables override default settings."""
    monkeypatch.setenv("APP_NAME", "RescuePay-Custom")
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "test_client_id_123")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "test_client_secret_xyz")

    settings = Settings(_env_file=None)
    assert settings.APP_NAME == "RescuePay-Custom"
    assert settings.APP_ENV == "testing"
    assert settings.DEBUG is True
    assert settings.PAYPAL_CLIENT_ID == "test_client_id_123"
    assert settings.PAYPAL_CLIENT_SECRET == "test_client_secret_xyz"


def test_config_loading_from_intended_env_path(tmp_path: Path) -> None:
    """Verify configuration loads properly from an explicit .env file path."""
    test_env = tmp_path / ".env"
    test_env.write_text("APP_NAME=RescuePay-From-Env\nDEBUG=true\n", encoding="utf-8")

    settings = Settings(_env_file=test_env)
    assert settings.APP_NAME == "RescuePay-From-Env"
    assert settings.DEBUG is True


def test_missing_paypal_credentials_do_not_prevent_startup() -> None:
    """Verify the application starts and functions without PayPal credentials configured."""
    settings = Settings(_env_file=None)
    assert settings.PAYPAL_CLIENT_ID == ""
    assert settings.PAYPAL_CLIENT_SECRET == ""

    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_secrets_masked_in_repr_and_str() -> None:
    """Verify sensitive PayPal credentials are not printed in console or repr outputs."""
    settings = Settings(
        _env_file=None,
        PAYPAL_CLIENT_SECRET="super-secret-credential-value",
    )
    repr_output = repr(settings)
    str_output = str(settings)

    assert "super-secret-credential-value" not in repr_output
    assert "super-secret-credential-value" not in str_output
    assert "******" in repr_output


def test_secrets_not_exposed_through_api_responses() -> None:
    """Verify API responses do not expose sensitive environment or PayPal settings."""
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()

    assert "PAYPAL_CLIENT_SECRET" not in payload
    assert "PAYPAL_CLIENT_ID" not in payload
    assert "client_secret" not in payload


def test_get_settings_caching_and_clear_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_settings returns a cached instance and clear_settings_cache resets it."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2

    monkeypatch.setenv("APP_NAME", "RescuePay-Modified")
    clear_settings_cache()
    s3 = get_settings()
    assert s3.APP_NAME == "RescuePay-Modified"
    assert s3 is not s1
