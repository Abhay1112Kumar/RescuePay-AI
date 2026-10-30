"""Shared pytest fixtures.

All PayPal traffic in the test suite goes through ``httpx.MockTransport``; no
real network calls are made. Tests never read the developer's ``.env``.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.v1.deps import get_paypal_client
from app.core.config import Settings, clear_settings_cache, get_settings
from app.integrations.paypal import OAUTH_TOKEN_PATH, PayPalClient
from app.main import app

TEST_CLIENT_ID = "test-client-id"
TEST_CLIENT_SECRET = "test-client-secret-do-not-leak"
TEST_ACCESS_TOKEN = "A21AAtest-access-token-do-not-leak"
SAMPLE_ORDER_ID = "5O190127TN364715T"


def make_settings(**overrides: Any) -> Settings:
    """Build Settings without reading .env, with sandbox-like test credentials."""
    values: dict[str, Any] = {
        "APP_ENV": "testing",
        "PAYPAL_CLIENT_ID": TEST_CLIENT_ID,
        "PAYPAL_CLIENT_SECRET": TEST_CLIENT_SECRET,
        "PAYPAL_BASE_URL": "https://api-m.sandbox.paypal.com",
        "PAYMENT_ALLOWED_CURRENCIES": "USD,EUR",
        "PAYMENT_MAX_AMOUNT": Decimal("1000.00"),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


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
    order_id: str = SAMPLE_ORDER_ID, status: str = "CREATED"
) -> dict[str, Any]:
    return {
        "id": order_id,
        "intent": "CAPTURE",
        "status": status,
        "create_time": "2026-10-30T12:00:00Z",
        "purchase_units": [
            {
                "reference_id": "RESCUE-1001",
                "amount": {"currency_code": "USD", "value": "25.00"},
            }
        ],
        "links": [],
    }


@dataclass
class FakePayPal:
    """Programmable fake PayPal server backed by httpx.MockTransport.

    ``routes`` maps ``(METHOD, path)`` to a response or a callable producing one.
    Every request is recorded in ``requests`` for assertions.
    """

    routes: dict[tuple[str, str], Any] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)
    token_calls: int = 0

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
        if callable(target):
            target = target()
        if isinstance(target, httpx.Response):
            return target
        return httpx.Response(200, json=target)

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


@pytest.fixture(autouse=True)
def _isolate_settings_and_state():
    """Keep cached settings and app-level state from leaking between tests."""
    clear_settings_cache()
    app.state.paypal_client = None
    app.dependency_overrides.clear()
    yield
    clear_settings_cache()
    app.state.paypal_client = None
    app.dependency_overrides.clear()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def fake_paypal() -> FakePayPal:
    return FakePayPal()


@pytest.fixture
def paypal_client(settings: Settings, fake_paypal: FakePayPal) -> PayPalClient:
    return make_paypal_client(settings, fake_paypal)


@pytest.fixture
def api_client(settings: Settings, paypal_client: PayPalClient) -> TestClient:
    """TestClient wired to test settings and the fake PayPal transport."""
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_paypal_client] = lambda: paypal_client
    with TestClient(app) as client:
        yield client
