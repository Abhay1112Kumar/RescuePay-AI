"""Tests for PaymentService business rules and PayPal payload construction."""

from decimal import Decimal

import httpx
import pytest

from app.core.exceptions import PaymentValidationError, PayPalAPIError
from app.integrations.paypal import ORDERS_PATH
from app.schemas.payment import CreateOrderRequest
from app.services.payment_service import PaymentService, format_amount
from tests.conftest import (
    SAMPLE_ORDER_ID,
    FakePayPal,
    created_order_response,
    make_settings,
    order_detail_response,
)


def _request(**overrides) -> CreateOrderRequest:
    data = {
        "reference_id": "RESCUE-1001",
        "currency": "USD",
        "amount": "25.00",
        "description": "Aid",
    }
    data.update(overrides)
    return CreateOrderRequest(**data)


@pytest.fixture
def service(settings, paypal_client) -> PaymentService:
    return PaymentService(paypal_client, settings)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("25"), "25.00"),
        (Decimal("25.5"), "25.50"),
        (Decimal("1E+2"), "100.00"),
        (Decimal("0.1"), "0.10"),
    ],
)
def test_format_amount(value: Decimal, expected: str) -> None:
    assert format_amount(value) == expected


def test_builds_paypal_payload(service: PaymentService, settings) -> None:
    payload = service.build_order_payload(_request(amount="25"))
    assert payload == {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": "RESCUE-1001",
                "description": "Aid",
                "amount": {"currency_code": "USD", "value": "25.00"},
            }
        ],
        "application_context": {
            "brand_name": settings.APP_NAME,
            "user_action": "PAY_NOW",
            "shipping_preference": "NO_SHIPPING",
            "return_url": settings.PAYPAL_RETURN_URL,
            "cancel_url": settings.PAYPAL_CANCEL_URL,
        },
    }


def test_payload_omits_description_when_absent(service: PaymentService) -> None:
    payload = service.build_order_payload(_request(description=None))
    assert "description" not in payload["purchase_units"][0]


async def test_rejects_unsupported_currency(
    service: PaymentService, fake_paypal: FakePayPal
) -> None:
    with pytest.raises(PaymentValidationError) as exc_info:
        await service.create_order(_request(currency="GBP"))
    assert "GBP" in exc_info.value.detail
    assert fake_paypal.requests == []  # PayPal never contacted


async def test_currency_is_case_insensitive_on_input() -> None:
    assert _request(currency="usd").currency == "USD"


async def test_rejects_amount_over_limit(
    service: PaymentService, fake_paypal: FakePayPal
) -> None:
    with pytest.raises(PaymentValidationError):
        await service.create_order(_request(amount="1000.01"))
    assert fake_paypal.requests == []


async def test_accepts_amount_at_limit(
    service: PaymentService, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.Response(201, json=created_order_response())
    )
    result = await service.create_order(_request(amount="1000.00"))
    assert result.order_id == SAMPLE_ORDER_ID


@pytest.mark.parametrize("amount", ["0", "-5", "25.001", "abc", ""])
def test_schema_rejects_bad_amounts(amount: str) -> None:
    with pytest.raises(ValueError):
        _request(amount=amount)


@pytest.mark.parametrize(
    "reference_id", ["", "-starts-with-dash", "has space", "semi;colon", "x" * 65]
)
def test_schema_rejects_bad_reference_ids(reference_id: str) -> None:
    with pytest.raises(ValueError):
        _request(reference_id=reference_id)


def test_schema_rejects_overlong_description() -> None:
    with pytest.raises(ValueError):
        _request(description="d" * 128)


async def test_create_order_returns_approval_link_and_request_id(
    service: PaymentService, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.Response(201, json=created_order_response())
    )
    result = await service.create_order(_request())

    assert result.order_id == SAMPLE_ORDER_ID
    assert result.status == "CREATED"
    approve = [link for link in result.links if link.rel == "approve"]
    assert len(approve) == 1
    assert "checkoutnow?token=" in approve[0].href

    sent = fake_paypal.requests_to("POST", ORDERS_PATH)[0]
    assert sent.headers["PayPal-Request-Id"] == result.request_id
    assert fake_paypal.body_of(sent)["purchase_units"][0]["amount"]["value"] == "25.00"


async def test_each_create_uses_fresh_request_id(
    service: PaymentService, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.Response(201, json=created_order_response())
    )
    a = await service.create_order(_request())
    b = await service.create_order(_request())
    assert a.request_id != b.request_id


async def test_accepts_payer_action_link_variant(
    service: PaymentService, fake_paypal: FakePayPal
) -> None:
    body = created_order_response()
    body["status"] = "PAYER_ACTION_REQUIRED"
    body["links"][1]["rel"] = "payer-action"
    fake_paypal.set("POST", ORDERS_PATH, httpx.Response(201, json=body))
    result = await service.create_order(_request())
    assert any(link.rel == "payer-action" for link in result.links)


async def test_missing_approval_link_is_an_error(
    service: PaymentService, fake_paypal: FakePayPal
) -> None:
    body = created_order_response()
    body["links"] = [body["links"][0]]  # only "self"
    fake_paypal.set("POST", ORDERS_PATH, httpx.Response(201, json=body))
    with pytest.raises(PayPalAPIError):
        await service.create_order(_request())


async def test_malformed_create_response_is_an_error(
    service: PaymentService, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.Response(201, json={"status": "CREATED"})
    )
    with pytest.raises(PayPalAPIError):
        await service.create_order(_request())


async def test_get_order_maps_fields(
    service: PaymentService, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "GET",
        f"{ORDERS_PATH}/{SAMPLE_ORDER_ID}",
        order_detail_response(status="APPROVED"),
    )
    result = await service.get_order(SAMPLE_ORDER_ID)
    assert result.order_id == SAMPLE_ORDER_ID
    assert result.status == "APPROVED"
    assert result.created_at is not None and result.created_at.year == 2026
    assert result.amount is not None
    assert (result.amount.currency_code, result.amount.value) == ("USD", "25.00")


async def test_get_order_tolerates_missing_purchase_units(
    service: PaymentService, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "GET",
        f"{ORDERS_PATH}/{SAMPLE_ORDER_ID}",
        {"id": SAMPLE_ORDER_ID, "status": "VOIDED"},
    )
    result = await service.get_order(SAMPLE_ORDER_ID)
    assert result.amount is None
    assert result.created_at is None


def test_allowed_currencies_parsing() -> None:
    s = make_settings(PAYMENT_ALLOWED_CURRENCIES=" usd, eur ,,inr ")
    assert s.allowed_currencies == frozenset({"USD", "EUR", "INR"})
