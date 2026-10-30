"""API tests for /api/v1/payments endpoints, including the error envelope."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.v1.deps import get_paypal_client
from app.core.config import clear_settings_cache
from app.integrations.paypal import ORDERS_PATH, PayPalClient
from app.main import app
from tests.conftest import (
    SAMPLE_CAPTURE_ID,
    SAMPLE_ORDER_ID,
    TEST_ACCESS_TOKEN,
    TEST_CLIENT_SECRET,
    FakePayPal,
    capture_path,
    capture_response,
    created_order_response,
    order_detail_response,
    order_path,
    paypal_error,
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


def _create(api_client: TestClient, fake: FakePayPal) -> dict:
    fake.set("POST", ORDERS_PATH, httpx.Response(201, json=created_order_response()))
    response = api_client.post(ORDERS_URL, json=VALID_BODY)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------- #
# Create
# ---------------------------------------------------------------------- #
def test_create_order_returns_201_contract_shape(api_client, fake_paypal) -> None:
    body = _create(api_client, fake_paypal)
    assert set(body) == {"order_id", "payment_id", "status", "request_id", "links"}
    assert body["order_id"] == SAMPLE_ORDER_ID
    assert body["status"] == "CREATED"
    assert len(body["payment_id"]) == 36
    assert {"href", "rel", "method"} == set(body["links"][0])
    assert any(link["rel"] == "approve" for link in body["links"])


def test_create_order_accepts_integer_amount(api_client, fake_paypal) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.Response(201, json=created_order_response())
    )
    response = api_client.post(ORDERS_URL, json={**VALID_BODY, "amount": 25})
    assert response.status_code == 201
    sent = fake_paypal.body_of(fake_paypal.requests_to("POST", ORDERS_PATH)[0])
    assert sent["purchase_units"][0]["amount"]["value"] == "25.00"


def test_create_order_schema_error_returns_422_envelope(
    api_client, fake_paypal
) -> None:
    response = api_client.post(ORDERS_URL, json={**VALID_BODY, "amount": "25.123"})
    assert response.status_code == 422
    _assert_envelope(response.json(), "REQUEST_VALIDATION_ERROR")
    assert isinstance(response.json()["detail"], list)
    assert fake_paypal.requests == []


def test_create_order_business_error_returns_400_envelope(
    api_client, fake_paypal
) -> None:
    response = api_client.post(ORDERS_URL, json={**VALID_BODY, "currency": "GBP"})
    assert response.status_code == 400
    _assert_envelope(response.json(), "PAYMENT_VALIDATION_FAILED")
    assert fake_paypal.requests == []


def test_create_order_missing_credentials_returns_503(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "")
    clear_settings_cache()
    with TestClient(app) as client:
        response = client.post(ORDERS_URL, json=VALID_BODY)
    assert response.status_code == 503
    _assert_envelope(response.json(), "PAYPAL_NOT_CONFIGURED")


def test_create_order_paypal_failure_returns_502_with_debug_id(
    api_client, fake_paypal
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

    http = httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL, transport=httpx.MockTransport(handler)
    )
    app.dependency_overrides[get_paypal_client] = lambda: PayPalClient(
        settings, http_client=http
    )
    with TestClient(app) as client:
        response = client.post(ORDERS_URL, json=VALID_BODY)
    assert response.status_code == 504
    _assert_envelope(response.json(), "PAYPAL_TIMEOUT")


# ---------------------------------------------------------------------- #
# Get
# ---------------------------------------------------------------------- #
def test_get_order_returns_200_contract_shape(api_client, fake_paypal) -> None:
    created = _create(api_client, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="APPROVED"))
    response = api_client.get(f"{ORDERS_URL}/{SAMPLE_ORDER_ID}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "order_id",
        "payment_id",
        "reference_id",
        "status",
        "paypal_status",
        "amount",
        "capture_id",
        "created_at",
        "updated_at",
    }
    assert body["payment_id"] == created["payment_id"]
    assert body["status"] == "APPROVED"
    assert body["paypal_status"] == "APPROVED"
    assert body["amount"] == {"currency_code": "USD", "value": "25.00"}
    assert body["capture_id"] is None
    assert body["created_at"].endswith("Z") or "+00:00" in body["created_at"]


def test_get_order_unknown_returns_404_envelope(api_client) -> None:
    response = api_client.get(f"{ORDERS_URL}/UNKNOWNORDER12345")
    assert response.status_code == 404
    _assert_envelope(response.json(), "ORDER_NOT_FOUND")


def test_get_order_malformed_id_returns_422_without_calling_paypal(
    api_client, fake_paypal
) -> None:
    response = api_client.get(f"{ORDERS_URL}/bad%20id!")
    assert response.status_code == 422
    assert fake_paypal.requests == []


# ---------------------------------------------------------------------- #
# Capture
# ---------------------------------------------------------------------- #
def _capture_url(order_id: str = SAMPLE_ORDER_ID) -> str:
    return f"{ORDERS_URL}/{order_id}/capture"


def test_capture_returns_200_contract_shape(api_client, fake_paypal) -> None:
    created = _create(api_client, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="APPROVED"))
    fake_paypal.set(
        "POST", capture_path(), httpx.Response(201, json=capture_response())
    )

    response = api_client.post(_capture_url(), json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"order_id", "payment_id", "capture_id", "status", "amount"}
    assert body["payment_id"] == created["payment_id"]
    assert body["capture_id"] == SAMPLE_CAPTURE_ID
    assert body["status"] == "COMPLETED"
    assert body["amount"] == {"currency_code": "USD", "value": "25.00"}


def test_capture_without_body_is_accepted(api_client, fake_paypal) -> None:
    _create(api_client, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="APPROVED"))
    fake_paypal.set(
        "POST", capture_path(), httpx.Response(201, json=capture_response())
    )
    assert api_client.post(_capture_url()).status_code == 200


def test_capture_twice_returns_same_result(api_client, fake_paypal) -> None:
    _create(api_client, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="APPROVED"))
    fake_paypal.set(
        "POST", capture_path(), httpx.Response(201, json=capture_response())
    )
    first = api_client.post(_capture_url()).json()
    second = api_client.post(_capture_url()).json()
    assert first == second
    assert len(fake_paypal.requests_to("POST", capture_path())) == 1


def test_capture_not_approved_returns_409(api_client, fake_paypal) -> None:
    _create(api_client, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="CREATED"))
    response = api_client.post(_capture_url())
    assert response.status_code == 409
    _assert_envelope(response.json(), "ORDER_NOT_APPROVED")


def test_capture_amount_mismatch_returns_409(api_client, fake_paypal) -> None:
    _create(api_client, fake_paypal)
    fake_paypal.set(
        "GET", order_path(), order_detail_response(status="APPROVED", value="999.00")
    )
    response = api_client.post(_capture_url())
    assert response.status_code == 409
    _assert_envelope(response.json(), "AMOUNT_MISMATCH")
    assert fake_paypal.requests_to("POST", capture_path()) == []


def test_capture_declined_returns_409(api_client, fake_paypal) -> None:
    _create(api_client, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="APPROVED"))
    fake_paypal.set(
        "POST",
        capture_path(),
        paypal_error(422, "UNPROCESSABLE_ENTITY", "INSTRUMENT_DECLINED", debug_id="dd"),
    )
    response = api_client.post(_capture_url())
    assert response.status_code == 409
    body = response.json()
    _assert_envelope(body, "PAYMENT_INSTRUMENT_DECLINED")
    assert body["paypal_debug_id"] == "dd"


def test_capture_unknown_order_returns_404(api_client) -> None:
    response = api_client.post(_capture_url("UNKNOWNORDER12345"))
    assert response.status_code == 404
    _assert_envelope(response.json(), "ORDER_NOT_FOUND")


def test_capture_after_timeout_returns_504_and_is_retryable(
    api_client, fake_paypal
) -> None:
    _create(api_client, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="APPROVED"))
    fake_paypal.set("POST", capture_path(), httpx.ReadTimeout("slow"))
    response = api_client.post(_capture_url())
    assert response.status_code == 504
    _assert_envelope(response.json(), "PAYPAL_TIMEOUT")

    fake_paypal.set(
        "POST", capture_path(), httpx.Response(201, json=capture_response())
    )
    retry = api_client.post(_capture_url())
    assert retry.status_code == 200
    assert retry.json()["status"] == "COMPLETED"


def test_status_reflects_capture(api_client, fake_paypal) -> None:
    _create(api_client, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="APPROVED"))
    fake_paypal.set(
        "POST", capture_path(), httpx.Response(201, json=capture_response())
    )
    api_client.post(_capture_url())
    body = api_client.get(f"{ORDERS_URL}/{SAMPLE_ORDER_ID}").json()
    assert body["status"] == "COMPLETED"
    assert body["capture_id"] == SAMPLE_CAPTURE_ID
    assert body["paypal_status"] is None  # terminal: no PayPal lookup needed


# ---------------------------------------------------------------------- #
# Cross-cutting
# ---------------------------------------------------------------------- #
def test_unknown_route_uses_error_envelope(api_client) -> None:
    response = api_client.get("/api/v1/nonexistent")
    assert response.status_code == 404
    _assert_envelope(response.json(), "RESOURCE_NOT_FOUND")


def test_no_secret_or_token_in_any_response(api_client, fake_paypal) -> None:
    _create(api_client, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="APPROVED"))
    fake_paypal.set(
        "POST", capture_path(), httpx.Response(201, json=capture_response())
    )
    for response in (
        api_client.post(ORDERS_URL, json={**VALID_BODY, "currency": "GBP"}),
        api_client.get(f"{ORDERS_URL}/{SAMPLE_ORDER_ID}"),
        api_client.post(_capture_url()),
    ):
        assert TEST_CLIENT_SECRET not in response.text
        assert TEST_ACCESS_TOKEN not in response.text


def test_token_is_reused_across_requests(api_client, fake_paypal) -> None:
    _create(api_client, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response())
    api_client.get(f"{ORDERS_URL}/{SAMPLE_ORDER_ID}")
    api_client.get(f"{ORDERS_URL}/{SAMPLE_ORDER_ID}")
    assert fake_paypal.token_calls == 1


def test_openapi_documents_payment_endpoints(api_client) -> None:
    spec = api_client.get("/api/v1/openapi.json").json()
    assert "/api/v1/payments/orders" in spec["paths"]
    assert "/api/v1/payments/orders/{order_id}" in spec["paths"]
    assert "/api/v1/payments/orders/{order_id}/capture" in spec["paths"]
