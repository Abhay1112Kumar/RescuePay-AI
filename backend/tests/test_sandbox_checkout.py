"""Application demo catalog and HTTP checkout contracts. Provider I/O is mocked."""

from uuid import uuid4

import pytest

from app.api.v1.checkout import checkout_return_origin, get_checkout_readiness
from app.api.v1.deps import get_payable_source
from app.core.config import clear_settings_cache
from app.core.exceptions import PaymentValidationError
from app.db.session import Database
from app.integrations.paypal import ORDERS_PATH
from app.main import app
from app.services.demo_catalog import DemoCatalog
from tests.conftest import (
    SAMPLE_ORDER_ID,
    capture_path,
    capture_response,
    created_order_response,
    order_detail_response,
    order_path,
)


def test_demo_catalog_is_fixed_usd_separate_from_synthetic_authority(
    api_client, fake_paypal
):
    response = api_client.get("/api/v1/sandbox/catalog")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "sandbox" and body["demo"] is True
    assert body["checkout_available"] is True
    assert body["blocking_reasons"] == []
    assert [(item["item_id"], item["amount"]) for item in body["items"]] == [
        ("demo-notebook-v1", {"currency_code": "USD", "value": "1.00"}),
        ("demo-stickers-v1", {"currency_code": "USD", "value": "2.50"}),
    ]
    assert fake_paypal.requests == []
    with pytest.raises(PaymentValidationError):
        DemoCatalog().resolve(
            "RESCUE-1001"
        )  # Old synthetic authority is not the demo catalog.


@pytest.mark.parametrize(
    "extra",
    [
        {"amount": "0.01"},
        {"currency": "EUR"},
        {"quantity": 10},
        {"reference_id": "other"},
    ],
)
def test_browser_cannot_supply_price_or_other_payable_fields(
    api_client, fake_paypal, extra
):
    response = api_client.post(
        "/api/v1/payments/orders",
        headers={"Idempotency-Key": str(uuid4())},
        json={"item_id": "demo-notebook-v1", **extra},
    )
    assert response.status_code == 422
    assert fake_paypal.requests == []


def test_mocked_end_to_end_demo_checkout_uses_only_backend_price(
    api_client, fake_paypal
):
    app.dependency_overrides.pop(get_payable_source)
    item = api_client.get("/api/v1/sandbox/catalog").json()["items"][0]
    headers = {"Idempotency-Key": str(uuid4())}
    body = {"item_id": item["item_id"]}
    fake_paypal.set("POST", ORDERS_PATH, created_order_response())
    first = api_client.post("/api/v1/payments/orders", headers=headers, json=body)
    assert first.status_code == 201
    sent = fake_paypal.body_of(fake_paypal.requests_to("POST", ORDERS_PATH)[0])
    unit = sent["purchase_units"][0]
    assert unit["amount"] == item["amount"]
    assert unit["reference_id"] == item["item_id"]
    assert "Sandbox demo only" in unit["description"]
    assert any(link["rel"] == "approve" for link in first.json()["links"])
    replay = api_client.post("/api/v1/payments/orders", headers=headers, json=body)
    assert replay.json()["payment_id"] == first.json()["payment_id"]

    fake_paypal.set(
        "GET", order_path(), order_detail_response(status="APPROVED", value="1.00")
    )
    lookup = api_client.get(f"/api/v1/payments/orders/{SAMPLE_ORDER_ID}")
    assert lookup.json()["status"] == "APPROVED"  # Approval is not paid.
    fake_paypal.set("POST", capture_path(), capture_response(value="1.00"))
    capture = api_client.post(f"/api/v1/payments/orders/{SAMPLE_ORDER_ID}/capture")
    assert capture.status_code == 200 and capture.json()["status"] == "COMPLETED"
    assert capture.json()["capture_id"]
    status = api_client.get(f"/api/v1/payments/orders/{SAMPLE_ORDER_ID}").json()
    assert status["payment_id"] == first.json()["payment_id"]
    assert status["reference_id"] == item["item_id"]
    assert status["amount"] == item["amount"]
    assert status["status"] == "COMPLETED"
    assert (
        api_client.post(f"/api/v1/payments/orders/{SAMPLE_ORDER_ID}/capture").json()
        == capture.json()
    )
    assert len(fake_paypal.requests_to("POST", ORDERS_PATH)) == 1
    assert len(fake_paypal.requests_to("POST", capture_path())) == 1


def test_explicit_checkout_flag_is_required_even_with_healthy_backend(
    api_client, fake_paypal, monkeypatch
):
    monkeypatch.setenv("SANDBOX_CHECKOUT_ENABLED", "false")
    clear_settings_cache()
    assert api_client.get("/api/v1/health").status_code == 200
    catalog = api_client.get("/api/v1/sandbox/catalog").json()
    assert catalog["checkout_available"] is False
    assert "SANDBOX_CHECKOUT_DISABLED" in catalog["blocking_reasons"]
    response = api_client.post(
        "/api/v1/payments/orders",
        headers={"Idempotency-Key": str(uuid4())},
        json={"item_id": "demo-notebook-v1"},
    )
    assert response.status_code == 503
    assert fake_paypal.requests == []


async def test_database_schema_must_be_ready(settings):
    database = Database("sqlite+aiosqlite:///:memory:")
    try:
        readiness = await get_checkout_readiness(settings, database)
        assert not readiness.checkout_available
        assert "DATABASE_NOT_READY" in readiness.blocking_reasons
    finally:
        await database.dispose()


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/payment/return",
        "http://127.0.0.1:5173/payment/return?token=other",
        "http://user:pass@localhost:5173/payment/return",
        "http://localhost:5173/other",
    ],
)
def test_redirect_configuration_is_local_and_matches_handlers(settings, url):
    assert (
        checkout_return_origin(settings.model_copy(update={"PAYPAL_RETURN_URL": url}))
        is None
    )
