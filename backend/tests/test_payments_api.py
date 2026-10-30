"""API tests for /api/v1/payments endpoints, including the error envelope."""

import httpx
from fastapi.testclient import TestClient

from app.api.v1.deps import get_paypal_client
from app.core.config import get_settings
from app.integrations.paypal import ORDERS_PATH
from app.main import app
from tests.conftest import (
    SAMPLE_ORDER_ID,
    TEST_ACCESS_TOKEN,
    TEST_CLIENT_SECRET,
    FakePayPal,
    created_order_response,
    make_settings,
    order_detail_response,
)

ORDERS_URL = "/api/v1/payments/orders"
VALID_BODY = {
    "reference_id": "RESCUE-1001",
    "currency": "USD",
    "amount": "25.00",
    "description": "Aid",
}

ENVELOPE_KEYS = {"detail", "error_code", "timestamp"}


def _assert_envelope(payload: dict, error_code: str) -> None:
    assert ENVELOPE_KEYS <= payload.keys()
    assert payload["error_code"] == error_code
    assert payload["timestamp"].endswith("Z")


def test_create_order_returns_201_contract_shape(
    api_client: TestClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.Response(201, json=created_order_response())
    )
    response = api_client.post(ORDERS_URL, json=VALID_BODY)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"order_id", "status", "request_id", "links"}
    assert body["order_id"] == SAMPLE_ORDER_ID
    assert body["status"] == "CREATED"
    assert {"href", "rel", "method"} == set(body["links"][0])
    assert any(link["rel"] == "approve" for link in body["links"])


def test_create_order_accepts_integer_amount(
    api_client: TestClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.Response(201, json=created_order_response())
    )
    response = api_client.post(ORDERS_URL, json={**VALID_BODY, "amount": 25})
    assert response.status_code == 201
    sent = fake_paypal.body_of(fake_paypal.requests_to("POST", ORDERS_PATH)[0])
    assert sent["purchase_units"][0]["amount"]["value"] == "25.00"


def test_create_order_schema_error_returns_422_envelope(
    api_client: TestClient, fake_paypal: FakePayPal
) -> None:
    response = api_client.post(ORDERS_URL, json={**VALID_BODY, "amount": "25.123"})
    assert response.status_code == 422
    _assert_envelope(response.json(), "REQUEST_VALIDATION_ERROR")
    assert isinstance(response.json()["detail"], list)
    assert fake_paypal.requests == []


def test_create_order_business_error_returns_400_envelope(
    api_client: TestClient, fake_paypal: FakePayPal
) -> None:
    response = api_client.post(ORDERS_URL, json={**VALID_BODY, "currency": "GBP"})
    assert response.status_code == 400
    _assert_envelope(response.json(), "PAYMENT_VALIDATION_FAILED")
    assert fake_paypal.requests == []


def test_create_order_missing_credentials_returns_503() -> None:
    app.dependency_overrides[get_settings] = lambda: make_settings(
        PAYPAL_CLIENT_ID="", PAYPAL_CLIENT_SECRET=""
    )
    with TestClient(app) as client:
        response = client.post(ORDERS_URL, json=VALID_BODY)
    assert response.status_code == 503
    _assert_envelope(response.json(), "PAYPAL_NOT_CONFIGURED")


def test_create_order_paypal_failure_returns_502_with_debug_id(
    api_client: TestClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST",
        ORDERS_PATH,
        httpx.Response(
            500,
            json={
                "name": "INTERNAL_SERVER_ERROR",
                "debug_id": "dbg-99",
                "message": "secret-ish",
            },
        ),
    )
    response = api_client.post(ORDERS_URL, json=VALID_BODY)
    assert response.status_code == 502
    body = response.json()
    _assert_envelope(body, "PAYPAL_API_ERROR")
    assert body["paypal_debug_id"] == "dbg-99"
    assert "secret-ish" not in response.text


def test_create_order_paypal_timeout_returns_504(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(
                200, json={"access_token": TEST_ACCESS_TOKEN, "expires_in": 3000}
            )
        raise httpx.ReadTimeout("slow", request=request)

    from app.integrations.paypal import PayPalClient

    http = httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL, transport=httpx.MockTransport(handler)
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_paypal_client] = lambda: PayPalClient(
        settings, http_client=http
    )
    with TestClient(app) as client:
        response = client.post(ORDERS_URL, json=VALID_BODY)
    assert response.status_code == 504
    _assert_envelope(response.json(), "PAYPAL_TIMEOUT")


def test_get_order_returns_200_contract_shape(
    api_client: TestClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "GET",
        f"{ORDERS_PATH}/{SAMPLE_ORDER_ID}",
        order_detail_response(status="APPROVED"),
    )
    response = api_client.get(f"{ORDERS_URL}/{SAMPLE_ORDER_ID}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"order_id", "status", "created_at", "amount"}
    assert body["status"] == "APPROVED"
    assert body["amount"] == {"currency_code": "USD", "value": "25.00"}
    assert body["created_at"].startswith("2026-10-30T12:00:00")


def test_get_order_unknown_returns_404_envelope(
    api_client: TestClient, fake_paypal: FakePayPal
) -> None:
    response = api_client.get(f"{ORDERS_URL}/UNKNOWNORDER12345")
    assert response.status_code == 404
    _assert_envelope(response.json(), "ORDER_NOT_FOUND")


def test_get_order_malformed_id_returns_422_without_calling_paypal(
    api_client: TestClient, fake_paypal: FakePayPal
) -> None:
    response = api_client.get(f"{ORDERS_URL}/bad%20id!")
    assert response.status_code == 422
    assert fake_paypal.requests == []


def test_unknown_route_uses_error_envelope(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/nonexistent")
    assert response.status_code == 404
    _assert_envelope(response.json(), "RESOURCE_NOT_FOUND")


def test_no_secret_or_token_in_any_response(
    api_client: TestClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.Response(201, json=created_order_response())
    )
    for response in (
        api_client.post(ORDERS_URL, json=VALID_BODY),
        api_client.post(ORDERS_URL, json={**VALID_BODY, "currency": "GBP"}),
        api_client.get(f"{ORDERS_URL}/{SAMPLE_ORDER_ID}"),
    ):
        assert TEST_CLIENT_SECRET not in response.text
        assert TEST_ACCESS_TOKEN not in response.text


def test_token_is_reused_across_requests(
    api_client: TestClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.Response(201, json=created_order_response())
    )
    fake_paypal.set("GET", f"{ORDERS_PATH}/{SAMPLE_ORDER_ID}", order_detail_response())
    api_client.post(ORDERS_URL, json=VALID_BODY)
    api_client.get(f"{ORDERS_URL}/{SAMPLE_ORDER_ID}")
    api_client.post(ORDERS_URL, json=VALID_BODY)
    assert fake_paypal.token_calls == 1


def test_openapi_documents_payment_endpoints(api_client: TestClient) -> None:
    spec = api_client.get("/api/v1/openapi.json").json()
    assert "/api/v1/payments/orders" in spec["paths"]
    assert "/api/v1/payments/orders/{order_id}" in spec["paths"]
    assert "post" in spec["paths"]["/api/v1/payments/orders"]
