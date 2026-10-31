"""Tests for PaymentService: persistence, business rules, capture safety."""

import asyncio
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from app.core.exceptions import (
    AmountMismatchError,
    CaptureInProgressError,
    CaptureUncertainError,
    OrderNotApprovedError,
    OrderNotFoundError,
    PaymentDeclinedError,
    PaymentStateError,
    PaymentValidationError,
    PayPalAPIError,
)
from app.integrations.paypal import ORDERS_PATH
from app.models.payment import Payment, PaymentEvent
from app.repositories.payment_repository import PaymentRepository
from app.schemas.payment import CreateOrderRequest
from app.services.payment_service import (
    PaymentService,
    format_amount,
    from_minor,
    to_minor,
)
from app.services.payment_state import PaymentStatus
from tests.conftest import (
    SAMPLE_CAPTURE_ID,
    SAMPLE_ORDER_ID,
    TEST_PAYABLES,
    FakePayPal,
    capture_path,
    capture_response,
    created_order_response,
    make_paypal_client,
    make_settings,
    order_detail_response,
    order_path,
    paypal_error,
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
def service(db_session, paypal_client, settings) -> PaymentService:
    return PaymentService(
        db_session, paypal_client, settings, payable_source=TEST_PAYABLES
    )


async def _create(service: PaymentService, fake: FakePayPal, **overrides):
    fake.set("POST", ORDERS_PATH, httpx.Response(201, json=created_order_response()))
    return await service.create_order(_request(**overrides))


async def _events(db_session, payment_id: str) -> list[str]:
    rows = await db_session.execute(
        select(PaymentEvent)
        .where(PaymentEvent.payment_id == payment_id)
        .order_by(PaymentEvent.id)
    )
    return [e.event_type for e in rows.scalars()]


async def _payment(db_session, payment_id: str) -> Payment:
    db_session.expire_all()
    payment = await db_session.get(Payment, payment_id)
    assert payment is not None
    return payment


# ---------------------------------------------------------------------- #
# Money helpers
# ---------------------------------------------------------------------- #
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


@pytest.mark.parametrize(
    ("major", "minor"),
    [("25.00", 2500), ("0.01", 1), ("1000", 100000), ("19.99", 1999)],
)
def test_minor_unit_round_trip(major: str, minor: int) -> None:
    assert to_minor(Decimal(major)) == minor
    assert from_minor(minor) == Decimal(major).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------- #
# Create order
# ---------------------------------------------------------------------- #
async def test_create_persists_record_and_audit_trail(
    service, fake_paypal, db_session
) -> None:
    result = await _create(service, fake_paypal)

    row = await _payment(db_session, result.payment_id)
    assert row.status == PaymentStatus.CREATED
    assert row.paypal_order_id == SAMPLE_ORDER_ID
    assert row.amount_minor == 2500
    assert row.currency == "USD"
    assert row.create_request_id == result.request_id
    assert await _events(db_session, row.id) == [
        "payment.created",
        "paypal.order.created",
    ]


async def test_create_sends_trusted_amount_and_custom_id(service, fake_paypal) -> None:
    result = await _create(service, fake_paypal, amount="25")
    sent = fake_paypal.body_of(fake_paypal.requests_to("POST", ORDERS_PATH)[0])
    unit = sent["purchase_units"][0]
    assert unit["amount"] == {"currency_code": "USD", "value": "25.00"}
    assert unit["custom_id"] == result.payment_id
    assert unit["reference_id"] == "RESCUE-1001"
    assert sent["intent"] == "CAPTURE"
    assert sent["application_context"]["user_action"] == "PAY_NOW"
    header = fake_paypal.requests_to("POST", ORDERS_PATH)[0].headers[
        "PayPal-Request-Id"
    ]
    assert header == result.request_id


async def test_create_returns_approval_link(service, fake_paypal) -> None:
    result = await _create(service, fake_paypal)
    assert result.status is PaymentStatus.CREATED
    assert any(link.rel == "approve" for link in result.links)


async def test_create_rejects_unsupported_currency_without_persisting(
    service, fake_paypal, db_session
) -> None:
    with pytest.raises(PaymentValidationError) as exc_info:
        await service.create_order(_request(currency="GBP"))
    assert "GBP" in exc_info.value.detail
    assert fake_paypal.requests == []
    assert (await db_session.execute(select(Payment))).scalars().all() == []


async def test_create_rejects_amount_over_limit(service, fake_paypal) -> None:
    with pytest.raises(PaymentValidationError):
        await service.create_order(_request(amount="1000.01"))
    assert fake_paypal.requests == []


async def test_create_accepts_amount_at_limit(service, fake_paypal) -> None:
    result = await _create(
        service, fake_paypal, amount="1000.00", reference_id="LIMIT-1000"
    )
    assert result.order_id == SAMPLE_ORDER_ID


@pytest.mark.parametrize("amount", ["0", "-5", "25.001", "abc", ""])
def test_schema_rejects_bad_amounts(amount: str) -> None:
    with pytest.raises(ValueError):
        _request(amount=amount)


@pytest.mark.parametrize(
    "reference_id", ["", "-dash", "has space", "semi;colon", "x" * 65]
)
def test_schema_rejects_bad_reference_ids(reference_id: str) -> None:
    with pytest.raises(ValueError):
        _request(reference_id=reference_id)


async def test_create_5xx_keeps_creation_uncertain(
    service, fake_paypal, db_session
) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, paypal_error(500, "INTERNAL_SERVER_ERROR", debug_id="d1")
    )
    with pytest.raises(PayPalAPIError):
        await service.create_order(_request())

    rows = (await db_session.execute(select(Payment))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == PaymentStatus.CREATION_UNCERTAIN
    assert rows[0].paypal_order_id is None
    assert await _events(db_session, rows[0].id) == [
        "payment.created",
        "paypal.order.create.failed",
    ]


async def test_create_missing_approval_link_keeps_creation_uncertain(
    service, fake_paypal, db_session
) -> None:
    body = created_order_response()
    body["links"] = [body["links"][0]]
    fake_paypal.set("POST", ORDERS_PATH, httpx.Response(201, json=body))
    with pytest.raises(PayPalAPIError):
        await service.create_order(_request())
    rows = (await db_session.execute(select(Payment))).scalars().all()
    assert rows[0].status == PaymentStatus.CREATION_UNCERTAIN


async def test_each_create_has_unique_request_id(service, fake_paypal) -> None:
    a = await _create(service, fake_paypal)
    fake_paypal.set(
        "POST",
        ORDERS_PATH,
        httpx.Response(201, json=created_order_response("ORDER2ABCDEFGHIJK")),
    )
    b = await service.create_order(_request())
    assert a.request_id != b.request_id
    assert a.payment_id != b.payment_id


# ---------------------------------------------------------------------- #
# Get order
# ---------------------------------------------------------------------- #
async def test_get_unknown_order_raises_not_found(service) -> None:
    with pytest.raises(OrderNotFoundError):
        await service.get_order("UNKNOWN0000000001")


async def test_get_syncs_approved_from_paypal(service, fake_paypal, db_session) -> None:
    created = await _create(service, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="APPROVED"))

    result = await service.get_order(SAMPLE_ORDER_ID)
    assert result.status is PaymentStatus.APPROVED
    assert result.paypal_status == "APPROVED"
    assert result.amount.value == "25.00"
    assert result.payment_id == created.payment_id
    assert result.created_at.tzinfo is not None
    assert (
        await _payment(db_session, created.payment_id)
    ).status == PaymentStatus.APPROVED


async def test_get_syncs_voided(service, fake_paypal, db_session) -> None:
    created = await _create(service, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="VOIDED"))
    result = await service.get_order(SAMPLE_ORDER_ID)
    assert result.status is PaymentStatus.VOIDED
    assert (
        await _payment(db_session, created.payment_id)
    ).status == PaymentStatus.VOIDED


async def test_get_records_out_of_band_capture(service, fake_paypal) -> None:
    await _create(service, fake_paypal)
    fake_paypal.set(
        "GET",
        order_path(),
        order_detail_response(
            status="COMPLETED",
            captures=[
                {
                    "id": "CAPX",
                    "status": "COMPLETED",
                    "final_capture": True,
                    "amount": {"currency_code": "USD", "value": "25.00"},
                }
            ],
        ),
    )
    result = await service.get_order(SAMPLE_ORDER_ID)
    assert result.status is PaymentStatus.COMPLETED
    assert result.capture_id == "CAPX"


async def test_get_returns_local_state_when_paypal_unavailable(
    service, fake_paypal
) -> None:
    await _create(service, fake_paypal)
    fake_paypal.set("GET", order_path(), paypal_error(503, "SERVICE_UNAVAILABLE"))
    result = await service.get_order(SAMPLE_ORDER_ID)
    assert result.status is PaymentStatus.CREATED
    assert result.paypal_status is None


async def test_get_does_not_call_paypal_for_terminal_payment(
    service, fake_paypal
) -> None:
    await _create(service, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="VOIDED"))
    await service.get_order(SAMPLE_ORDER_ID)
    calls_before = len(fake_paypal.requests_to("GET", order_path()))
    await service.get_order(SAMPLE_ORDER_ID)
    assert len(fake_paypal.requests_to("GET", order_path())) == calls_before


# ---------------------------------------------------------------------- #
# Capture
# ---------------------------------------------------------------------- #
async def _approved(service, fake_paypal):
    created = await _create(service, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="APPROVED"))
    return created


async def test_capture_success(service, fake_paypal, db_session) -> None:
    created = await _approved(service, fake_paypal)
    fake_paypal.set(
        "POST", capture_path(), httpx.Response(201, json=capture_response())
    )

    result = await service.capture_order(SAMPLE_ORDER_ID)
    assert result.status is PaymentStatus.COMPLETED
    assert result.capture_id == SAMPLE_CAPTURE_ID
    assert result.amount.value == "25.00"

    row = await _payment(db_session, created.payment_id)
    assert row.status == PaymentStatus.COMPLETED
    assert row.paypal_capture_id == SAMPLE_CAPTURE_ID
    assert row.capture_request_id is not None
    sent = fake_paypal.requests_to("POST", capture_path())[0]
    assert sent.headers["PayPal-Request-Id"] == row.capture_request_id
    assert sent.headers["Prefer"] == "return=representation"
    assert await _events(db_session, row.id) == [
        "payment.created",
        "paypal.order.created",
        "payment.capture.started",
        "paypal.capture.completed",
    ]


async def test_capture_is_idempotent(service, fake_paypal) -> None:
    await _approved(service, fake_paypal)
    fake_paypal.set(
        "POST", capture_path(), httpx.Response(201, json=capture_response())
    )
    first = await service.capture_order(SAMPLE_ORDER_ID)
    second = await service.capture_order(SAMPLE_ORDER_ID)
    assert first == second
    assert len(fake_paypal.requests_to("POST", capture_path())) == 1


async def test_capture_refused_when_not_approved(
    service, fake_paypal, db_session
) -> None:
    created = await _create(service, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="CREATED"))
    with pytest.raises(OrderNotApprovedError):
        await service.capture_order(SAMPLE_ORDER_ID)
    assert fake_paypal.requests_to("POST", capture_path()) == []
    assert (
        await _payment(db_session, created.payment_id)
    ).status == PaymentStatus.CREATED


async def test_capture_refused_on_amount_mismatch(
    service, fake_paypal, db_session
) -> None:
    created = await _create(service, fake_paypal)
    fake_paypal.set(
        "GET", order_path(), order_detail_response(status="APPROVED", value="250.00")
    )
    with pytest.raises(AmountMismatchError):
        await service.capture_order(SAMPLE_ORDER_ID)
    assert fake_paypal.requests_to("POST", capture_path()) == []
    row = await _payment(db_session, created.payment_id)
    assert row.status == PaymentStatus.FAILED
    assert "paypal.capture.amount_mismatch" in await _events(db_session, row.id)


async def test_capture_refused_on_currency_mismatch(service, fake_paypal) -> None:
    await _create(service, fake_paypal)
    fake_paypal.set(
        "GET", order_path(), order_detail_response(status="APPROVED", currency="EUR")
    )
    with pytest.raises(AmountMismatchError):
        await service.capture_order(SAMPLE_ORDER_ID)


async def test_capture_when_paypal_already_completed_reconciles(
    service, fake_paypal
) -> None:
    await _create(service, fake_paypal)
    fake_paypal.set(
        "GET",
        order_path(),
        order_detail_response(
            status="COMPLETED",
            captures=[
                {
                    "id": "CAPY",
                    "status": "COMPLETED",
                    "final_capture": True,
                    "amount": {"currency_code": "USD", "value": "25.00"},
                }
            ],
        ),
    )
    result = await service.capture_order(SAMPLE_ORDER_ID)
    assert result.status is PaymentStatus.COMPLETED
    assert result.capture_id == "CAPY"
    assert fake_paypal.requests_to("POST", capture_path()) == []


async def test_capture_voided_order(service, fake_paypal, db_session) -> None:
    created = await _create(service, fake_paypal)
    fake_paypal.set("GET", order_path(), order_detail_response(status="VOIDED"))
    with pytest.raises(PaymentStateError):
        await service.capture_order(SAMPLE_ORDER_ID)
    assert (
        await _payment(db_session, created.payment_id)
    ).status == PaymentStatus.VOIDED


async def test_capture_timeout_then_paypal_shows_completed_recovers(
    service, fake_paypal, db_session
) -> None:
    created = await _approved(service, fake_paypal)
    fake_paypal.set("POST", capture_path(), httpx.ReadTimeout("slow"))
    # After the timeout the service re-reads the order: PayPal says it went through.
    lookups = {"n": 0}

    def order_lookup():
        lookups["n"] += 1
        if lookups["n"] == 1:
            return order_detail_response(status="APPROVED")
        return order_detail_response(
            status="COMPLETED",
            captures=[
                capture_response()["purchase_units"][0]["payments"]["captures"][0]
            ],
        )

    fake_paypal.set("GET", order_path(), order_lookup)
    result = await service.capture_order(SAMPLE_ORDER_ID)
    assert result.status is PaymentStatus.COMPLETED
    assert result.capture_id == SAMPLE_CAPTURE_ID
    events = await _events(db_session, created.payment_id)
    assert "paypal.order.lookup.completed" in events


async def test_capture_timeout_stays_uncertain_and_reconciles_without_retry(
    service, fake_paypal, db_session
) -> None:
    created = await _approved(service, fake_paypal)
    fake_paypal.set("POST", capture_path(), httpx.ReadTimeout("slow"))
    with pytest.raises(CaptureUncertainError):
        await service.capture_order(SAMPLE_ORDER_ID)
    row = await _payment(db_session, created.payment_id)
    assert row.status == PaymentStatus.CAPTURE_UNCERTAIN
    request_id = row.capture_request_id
    with pytest.raises(CaptureUncertainError):
        await service.capture_order(SAMPLE_ORDER_ID)
    fake_paypal.set(
        "GET",
        order_path(),
        order_detail_response(
            status="COMPLETED",
            captures=[
                capture_response()["purchase_units"][0]["payments"]["captures"][0]
            ],
        ),
    )
    result = await service.capture_order(SAMPLE_ORDER_ID)
    assert result.status is PaymentStatus.COMPLETED
    requests = fake_paypal.requests_to("POST", capture_path())
    assert len(requests) == 1
    assert requests[0].headers["PayPal-Request-Id"] == request_id


async def test_capture_5xx_is_treated_as_uncertain(
    service, fake_paypal, db_session
) -> None:
    created = await _approved(service, fake_paypal)
    fake_paypal.set("POST", capture_path(), paypal_error(500, "INTERNAL_SERVER_ERROR"))
    with pytest.raises(CaptureUncertainError):
        await service.capture_order(SAMPLE_ORDER_ID)
    row = await _payment(db_session, created.payment_id)
    assert row.status == PaymentStatus.CAPTURE_UNCERTAIN


async def test_capture_instrument_declined(service, fake_paypal, db_session) -> None:
    created = await _approved(service, fake_paypal)
    fake_paypal.set(
        "POST",
        capture_path(),
        paypal_error(422, "UNPROCESSABLE_ENTITY", "INSTRUMENT_DECLINED"),
    )
    with pytest.raises(PaymentDeclinedError) as exc_info:
        await service.capture_order(SAMPLE_ORDER_ID)
    assert exc_info.value.status_code == 409
    assert (
        await _payment(db_session, created.payment_id)
    ).status == PaymentStatus.APPROVED


async def test_capture_order_not_approved_issue(
    service, fake_paypal, db_session
) -> None:
    created = await _approved(service, fake_paypal)
    fake_paypal.set(
        "POST",
        capture_path(),
        paypal_error(422, "UNPROCESSABLE_ENTITY", "ORDER_NOT_APPROVED"),
    )
    with pytest.raises(OrderNotApprovedError):
        await service.capture_order(SAMPLE_ORDER_ID)
    assert (
        await _payment(db_session, created.payment_id)
    ).status == PaymentStatus.CREATED


async def test_capture_already_captured_issue_reconciles(service, fake_paypal) -> None:
    await _approved(service, fake_paypal)
    fake_paypal.set(
        "POST",
        capture_path(),
        paypal_error(422, "UNPROCESSABLE_ENTITY", "ORDER_ALREADY_CAPTURED"),
    )
    lookups = {"n": 0}

    def order_lookup():
        lookups["n"] += 1
        if lookups["n"] == 1:
            return order_detail_response(status="APPROVED")
        return order_detail_response(
            status="COMPLETED",
            captures=[
                capture_response()["purchase_units"][0]["payments"]["captures"][0]
            ],
        )

    fake_paypal.set("GET", order_path(), order_lookup)
    result = await service.capture_order(SAMPLE_ORDER_ID)
    assert result.status is PaymentStatus.COMPLETED


async def test_unclassified_capture_error_requires_reconciliation(
    service, fake_paypal, db_session
) -> None:
    created = await _approved(service, fake_paypal)
    fake_paypal.set(
        "POST",
        capture_path(),
        paypal_error(422, "UNPROCESSABLE_ENTITY", "TRANSACTION_REFUSED"),
    )
    with pytest.raises(CaptureUncertainError):
        await service.capture_order(SAMPLE_ORDER_ID)
    row = await _payment(db_session, created.payment_id)
    assert row.status == PaymentStatus.CAPTURE_UNCERTAIN


async def test_capture_pending_settlement(service, fake_paypal, db_session) -> None:
    created = await _approved(service, fake_paypal)
    fake_paypal.set(
        "POST",
        capture_path(),
        httpx.Response(201, json=capture_response(capture_status="PENDING")),
    )
    result = await service.capture_order(SAMPLE_ORDER_ID)
    assert result.status is PaymentStatus.CAPTURE_PENDING
    assert result.capture_id == SAMPLE_CAPTURE_ID
    assert (
        await _payment(db_session, created.payment_id)
    ).status == PaymentStatus.CAPTURE_PENDING

    # Replay returns the pending state without calling PayPal again.
    again = await service.capture_order(SAMPLE_ORDER_ID)
    assert again.status is PaymentStatus.CAPTURE_PENDING
    assert len(fake_paypal.requests_to("POST", capture_path())) == 1

    # A later lookup showing settlement completes the payment.
    fake_paypal.set(
        "GET",
        order_path(),
        order_detail_response(
            status="COMPLETED",
            captures=[
                capture_response()["purchase_units"][0]["payments"]["captures"][0]
            ],
        ),
    )
    status = await service.get_order(SAMPLE_ORDER_ID)
    assert status.status is PaymentStatus.COMPLETED


async def test_capture_declined_capture_status_marks_failed(
    service, fake_paypal, db_session
) -> None:
    created = await _approved(service, fake_paypal)
    fake_paypal.set(
        "POST",
        capture_path(),
        httpx.Response(201, json=capture_response(capture_status="DECLINED")),
    )
    result = await service.capture_order(SAMPLE_ORDER_ID)
    assert result.status is PaymentStatus.FAILED
    assert (
        await _payment(db_session, created.payment_id)
    ).status == PaymentStatus.FAILED


async def test_capture_on_failed_payment_is_rejected(service, fake_paypal) -> None:
    await _create(service, fake_paypal)
    fake_paypal.set(
        "GET", order_path(), order_detail_response(status="APPROVED", value="1.00")
    )
    with pytest.raises(AmountMismatchError):
        await service.capture_order(SAMPLE_ORDER_ID)
    with pytest.raises(PaymentStateError) as exc_info:
        await service.capture_order(SAMPLE_ORDER_ID)
    assert exc_info.value.error_code == "PAYMENT_INVALID_STATE"


async def test_capture_unknown_order(service) -> None:
    with pytest.raises(OrderNotFoundError):
        await service.capture_order("UNKNOWN0000000001")


async def test_capture_lock_blocks_second_caller(
    service, fake_paypal, db_session, database, paypal_client, settings
) -> None:
    created = await _approved(service, fake_paypal)
    # Simulate another process holding the lock.
    repo = PaymentRepository(db_session)
    assert await repo.try_begin_capture(created.payment_id)
    await db_session.commit()

    async with database.session_factory() as other_session:
        other = PaymentService(
            other_session, paypal_client, settings, payable_source=TEST_PAYABLES
        )
        with pytest.raises(CaptureInProgressError):
            await other.capture_order(SAMPLE_ORDER_ID)
    assert fake_paypal.requests_to("POST", capture_path()) == []


async def test_try_begin_capture_is_atomic(service, fake_paypal, database) -> None:
    created = await _approved(service, fake_paypal)

    async def attempt() -> bool:
        async with database.session_factory() as s:
            won = await PaymentRepository(s).try_begin_capture(created.payment_id)
            await s.commit()
            return won

    results = await asyncio.gather(*(attempt() for _ in range(5)))
    assert sum(results) == 1


async def test_concurrent_captures_charge_once(fake_paypal, database, settings) -> None:
    """Two concurrent capture requests: one captures, the other is told to wait."""
    client = make_paypal_client(settings, fake_paypal)

    async with database.session_factory() as s:
        created = await _create(
            PaymentService(s, client, settings, payable_source=TEST_PAYABLES),
            fake_paypal,
        )
    fake_paypal.set("GET", order_path(), order_detail_response(status="APPROVED"))

    async def slow_capture():
        await asyncio.sleep(0.05)
        return httpx.Response(201, json=capture_response(payment_id=created.payment_id))

    async def handler(request: httpx.Request) -> httpx.Response:
        fake_paypal.requests.append(request)
        if request.url.path == capture_path():
            return await slow_capture()
        return fake_paypal.handler(request)

    http = httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL, transport=httpx.MockTransport(handler)
    )
    from app.integrations.paypal import PayPalClient

    shared = PayPalClient(settings, http_client=http)

    async def attempt():
        async with database.session_factory() as s:
            try:
                return await PaymentService(
                    s, shared, settings, payable_source=TEST_PAYABLES
                ).capture_order(SAMPLE_ORDER_ID)
            except CaptureInProgressError as exc:
                return exc

    a, b = await asyncio.gather(attempt(), attempt())
    outcomes = sorted(type(x).__name__ for x in (a, b))
    assert outcomes == ["CaptureInProgressError", "CaptureResponse"]
    assert len([r for r in fake_paypal.requests if r.url.path == capture_path()]) == 1

    async with database.session_factory() as s:
        row = await s.get(Payment, created.payment_id)
        assert row.status == PaymentStatus.COMPLETED


def test_allowed_currencies_parsing() -> None:
    s = make_settings(PAYMENT_ALLOWED_CURRENCIES=" usd, eur ,,inr ")
    assert s.allowed_currencies == frozenset({"USD", "EUR", "INR"})
