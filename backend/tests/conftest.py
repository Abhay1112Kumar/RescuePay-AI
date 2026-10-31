"""Shared pytest fixtures.

All PayPal traffic in the test suite goes through ``httpx.MockTransport``; no
real network calls are made. Each test gets a fresh SQLite database under
``tmp_path``. Settings come from environment variables set per test, so the
developer's ``.env`` credentials are never used.
"""

import json
from collections.abc import AsyncIterator, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_payable_source, get_paypal_client
from app.core.config import Settings, clear_settings_cache, get_settings
from app.core.exceptions import PaymentValidationError
from app.db.session import Database
from app.integrations.paypal import OAUTH_TOKEN_PATH, ORDERS_PATH, PayPalClient
from app.main import app
from app.services.payables import Payable

TEST_CLIENT_ID = "test-client-id"
TEST_CLIENT_SECRET = "test-client-secret-do-not-leak"
TEST_ACCESS_TOKEN = "A21AAtest-access-token-do-not-leak"
SAMPLE_ORDER_ID = "5O190127TN364715T"
SAMPLE_CAPTURE_ID = "1JS80234KJ293810L"
TEST_MERCHANT_ID = "TESTMERCHANT1"
_PAYMENT_ID = "__CREATED_PAYMENT_ID__"


class FixedTestPayables:
    """Synthetic test authority only; not a shipped catalog or business model."""

    def resolve(self, reference_id: str) -> Payable:
        amounts = {"RESCUE-1001": Decimal("25.00"), "LIMIT-1000": Decimal("1000.00")}
        if reference_id not in amounts:
            raise PaymentValidationError("Unknown synthetic test payable.")
        return Payable(reference_id, "USD", amounts[reference_id])


TEST_PAYABLES = FixedTestPayables()


def test_env(db_path: Path) -> dict[str, str]:
    """Environment variables that define the test configuration."""
    return {
        "APP_ENV": "testing",
        "SANDBOX_CHECKOUT_ENABLED": "true",
        "PAYPAL_CLIENT_ID": TEST_CLIENT_ID,
        "PAYPAL_CLIENT_SECRET": TEST_CLIENT_SECRET,
        "PAYPAL_MERCHANT_ID": TEST_MERCHANT_ID,
        "PAYPAL_BASE_URL": "https://api-m.sandbox.paypal.com",
        "PAYMENT_ALLOWED_CURRENCIES": "USD,EUR",
        "PAYMENT_MAX_AMOUNT": "1000.00",
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
        "DATABASE_AUTO_CREATE": "true",
    }


def make_settings(**overrides: Any) -> Settings:
    """Build Settings without reading .env, with sandbox-like test credentials."""
    values: dict[str, Any] = {
        "APP_ENV": "testing",
        "PAYPAL_CLIENT_ID": TEST_CLIENT_ID,
        "PAYPAL_CLIENT_SECRET": TEST_CLIENT_SECRET,
        "PAYPAL_MERCHANT_ID": TEST_MERCHANT_ID,
        "PAYPAL_BASE_URL": "https://api-m.sandbox.paypal.com",
        "PAYMENT_ALLOWED_CURRENCIES": "USD,EUR",
        "PAYMENT_MAX_AMOUNT": Decimal("1000.00"),
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


# ---------------------------------------------------------------------- #
# PayPal response builders
# ---------------------------------------------------------------------- #
def token_response(expires_in: int = 32400) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "scope": "https://uri.paypal.com/services/payments/payment",
            "access_token": TEST_ACCESS_TOKEN,
            "token_type": "Bearer",
            "app_id": "APP-80W284485P519543T",
            "expires_in": expires_in,
            "nonce": "nonce",
        },
    )


def created_order_response(order_id: str = SAMPLE_ORDER_ID) -> dict[str, Any]:
    return {
        "id": order_id,
        "status": "CREATED",
        "links": [
            {
                "href": f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{order_id}",
                "rel": "self",
                "method": "GET",
            },
            {
                "href": f"https://www.sandbox.paypal.com/checkoutnow?token={order_id}",
                "rel": "approve",
                "method": "GET",
            },
            {
                "href": f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{order_id}/capture",
                "rel": "capture",
                "method": "POST",
            },
        ],
    }


def order_detail_response(
    order_id: str = SAMPLE_ORDER_ID,
    status: str = "CREATED",
    *,
    currency: str = "USD",
    value: str = "25.00",
    captures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    unit: dict[str, Any] = {
        "reference_id": "RESCUE-1001",
        "custom_id": _PAYMENT_ID,
        "payee": {"merchant_id": TEST_MERCHANT_ID},
        "amount": {"currency_code": currency, "value": value},
    }
    if captures is not None:
        unit["payments"] = {"captures": captures}
    return {
        "id": order_id,
        "intent": "CAPTURE",
        "status": status,
        "create_time": "2026-10-30T12:00:00Z",
        "purchase_units": [unit],
        "links": [],
    }


def capture_detail(
    capture_id: str = SAMPLE_CAPTURE_ID,
    status: str = "COMPLETED",
    *,
    currency: str = "USD",
    value: str = "25.00",
) -> dict[str, Any]:
    return {
        "id": capture_id,
        "status": status,
        "amount": {"currency_code": currency, "value": value},
        "final_capture": True,
    }


def capture_response(
    order_id: str = SAMPLE_ORDER_ID,
    capture_id: str = SAMPLE_CAPTURE_ID,
    capture_status: str = "COMPLETED",
    *,
    currency: str = "USD",
    value: str = "25.00",
    payment_id: str = _PAYMENT_ID,
) -> dict[str, Any]:
    """Body of a successful POST /v2/checkout/orders/{id}/capture."""
    order_status = "COMPLETED" if capture_status == "COMPLETED" else "COMPLETED"
    return {
        "id": order_id,
        "intent": "CAPTURE",
        "status": order_status,
        "purchase_units": [
            {
                "reference_id": "RESCUE-1001",
                "custom_id": payment_id,
                "payee": {"merchant_id": TEST_MERCHANT_ID},
                "amount": {"currency_code": currency, "value": value},
                "payments": {
                    "captures": [
                        capture_detail(
                            capture_id, capture_status, currency=currency, value=value
                        )
                    ]
                },
            }
        ],
        "links": [],
    }


def paypal_error(
    status: int, name: str, issue: str | None = None, debug_id: str = "dbg"
) -> httpx.Response:
    body: dict[str, Any] = {"name": name, "message": "x", "debug_id": debug_id}
    if issue:
        body["details"] = [{"issue": issue, "description": "d"}]
    return httpx.Response(status, json=body)


def order_path(order_id: str = SAMPLE_ORDER_ID) -> str:
    return f"{ORDERS_PATH}/{order_id}"


def capture_path(order_id: str = SAMPLE_ORDER_ID) -> str:
    return f"{ORDERS_PATH}/{order_id}/capture"


# ---------------------------------------------------------------------- #
# Fake PayPal transport
# ---------------------------------------------------------------------- #
@dataclass
class FakePayPal:
    """Programmable fake PayPal server backed by httpx.MockTransport.

    ``routes`` maps ``(METHOD, path)`` to a response, a dict (200 JSON), a
    callable producing either, or an exception instance to raise (transport
    failures). Every request is recorded in ``requests``.
    """

    routes: dict[tuple[str, str], Any] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)
    token_calls: int = 0
    created_units: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.routes.setdefault(("POST", OAUTH_TOKEN_PATH), token_response)

    def set(self, method: str, path: str, response: Any) -> None:
        self.routes[(method.upper(), path)] = response

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method.upper(), request.url.path)
        if key == ("POST", OAUTH_TOKEN_PATH):
            self.token_calls += 1
        target = self.routes.get(key)
        if target is None:
            return httpx.Response(
                404, json={"name": "RESOURCE_NOT_FOUND", "debug_id": "nf"}
            )
        if callable(target) and not isinstance(target, Exception):
            target = target()
        if isinstance(target, Exception):
            if isinstance(target, httpx.RequestError) and target._request is None:  # noqa: SLF001
                target.request = request
            raise target
        status_code = target.status_code if isinstance(target, httpx.Response) else 200
        if isinstance(target, httpx.Response):
            try:
                body = target.json()
            except ValueError:
                return target
        else:
            body = deepcopy(target)
        if isinstance(body, dict):
            if (
                request.method == "POST"
                and request.url.path == ORDERS_PATH
                and 200 <= status_code < 300
            ):
                units = self.body_of(request).get("purchase_units")
                if units:
                    self.created_units[body.get("id")] = units[0]
            for unit in body.get("purchase_units", []):
                if isinstance(unit, dict) and unit.get("custom_id") == _PAYMENT_ID:
                    expected = self.created_units.get(body.get("id"))
                    if expected:
                        unit["custom_id"] = expected["custom_id"]
                        unit["reference_id"] = expected["reference_id"]
        return httpx.Response(status_code, json=body)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def body_of(self, request: httpx.Request) -> dict[str, Any]:
        return json.loads(request.content.decode()) if request.content else {}

    def requests_to(self, method: str, path: str) -> list[httpx.Request]:
        return [
            r
            for r in self.requests
            if r.method.upper() == method.upper() and r.url.path == path
        ]


def make_paypal_client(
    settings: Settings,
    fake: FakePayPal,
    clock: Callable[[], float] | None = None,
) -> PayPalClient:
    http = httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL, transport=fake.transport()
    )
    kwargs: dict[str, Any] = {}
    if clock is not None:
        kwargs["clock"] = clock
    return PayPalClient(settings, http_client=http, **kwargs)


# ---------------------------------------------------------------------- #
# Fixtures
# ---------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _isolate_settings_and_state():
    """Keep cached settings and app-level state from leaking between tests."""
    clear_settings_cache()
    app.state.paypal_client = None
    app.state.database = None
    app.dependency_overrides.clear()
    yield
    clear_settings_cache()
    app.state.paypal_client = None
    app.state.database = None
    app.dependency_overrides.clear()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> Settings:
    """Test settings installed via environment so app startup sees the same values."""
    for key, value in test_env(db_path).items():
        monkeypatch.setenv(key, value)
    clear_settings_cache()
    return get_settings()


@pytest.fixture
def fake_paypal() -> FakePayPal:
    return FakePayPal()


@pytest.fixture
def paypal_client(settings: Settings, fake_paypal: FakePayPal) -> PayPalClient:
    return make_paypal_client(settings, fake_paypal)


@pytest.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    db = Database.from_settings(settings)
    await db.create_all()
    yield db
    await db.dispose()


@pytest.fixture
async def db_session(database: Database) -> AsyncIterator[AsyncSession]:
    async with database.session_factory() as session:
        yield session


@pytest.fixture
def api_client(settings: Settings, paypal_client: PayPalClient) -> TestClient:
    """TestClient wired to test settings (via env), a temp DB, and the fake PayPal."""
    app.dependency_overrides[get_paypal_client] = lambda: paypal_client
    app.dependency_overrides[get_payable_source] = lambda: TEST_PAYABLES
    with TestClient(app) as client:
        yield client
