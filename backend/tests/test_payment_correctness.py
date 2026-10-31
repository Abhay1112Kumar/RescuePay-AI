"""Regression evidence for payment safety. All provider responses are synthetic."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.core.exceptions import (
    CaptureInProgressError,
    CaptureUncertainError,
    RescuePayError,
)
from app.integrations.paypal import ORDERS_PATH
from app.models.payment import Payment
from app.repositories.payment_repository import PaymentRepository
from app.schemas.payment import CreateOrderRequest
from app.services.payment_service import PaymentService
from tests.conftest import (
    SAMPLE_ORDER_ID,
    TEST_PAYABLES,
    capture_path,
    capture_response,
    created_order_response,
    make_paypal_client,
    order_detail_response,
    order_path,
)


@pytest.fixture
def service(db_session, paypal_client, settings):
    return PaymentService(
        db_session, paypal_client, settings, payable_source=TEST_PAYABLES
    )


async def created(service, fake, db_session):
    fake.set("POST", ORDERS_PATH, created_order_response())
    response = await service.create_order(
        CreateOrderRequest(reference_id="RESCUE-1001", currency="USD", amount="25.00")
    )
    payment = await db_session.get(Payment, response.payment_id)
    return payment


def identified(body, payment):
    unit = body["purchase_units"][0]
    unit["custom_id"] = payment.id
    unit["payee"] = {"merchant_id": "TESTMERCHANT1"}
    return body


@pytest.mark.parametrize(
    "overrides",
    [
        {"PAYPAL_MODE": "live"},
        {"PAYPAL_BASE_URL": "https://api-m.paypal.com"},
        {"PAYPAL_BASE_URL": "https://example.com"},
        {"PAYPAL_BASE_URL": "https://api-m.sandbox.paypal.com.evil.test"},
        {"PAYPAL_BASE_URL": "http://api-m.sandbox.paypal.com"},
        {"PAYPAL_BASE_URL": "https://api-m.sandbox.paypal.com/other"},
    ],
)
def test_reject_non_sandbox_targets(overrides):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **overrides)


@pytest.mark.parametrize(
    "damage",
    [
        "amount",
        "currency",
        "id",
        "missing",
        "multiple",
        "empty_id",
        "no_amount",
        "not_final",
        "unknown_status",
    ],
)
async def test_invalid_capture_evidence_never_becomes_success(
    service, fake_paypal, db_session, damage
):
    payment = await created(service, fake_paypal, db_session)
    fake_paypal.set(
        "GET",
        order_path(),
        identified(order_detail_response(status="APPROVED"), payment),
    )
    body = identified(capture_response(), payment)
    capture = body["purchase_units"][0]["payments"]["captures"][0]
    if damage == "amount":
        capture["amount"]["value"] = "0.01"
    elif damage == "currency":
        capture["amount"]["currency_code"] = "EUR"
    elif damage == "id":
        body["id"] = "WRONGORDER12345"
    elif damage == "missing":
        del body["purchase_units"][0]["payments"]
    elif damage == "multiple":
        body["purchase_units"][0]["payments"]["captures"].append(
            dict(capture, id="SECOND")
        )
    elif damage == "empty_id":
        capture["id"] = ""
    elif damage == "no_amount":
        del capture["amount"]
    elif damage == "not_final":
        capture["final_capture"] = False
    else:
        capture["status"] = "UNKNOWN"
    fake_paypal.set("POST", capture_path(), body)
    try:
        await service.capture_order(SAMPLE_ORDER_ID)
    except RescuePayError:
        pass
    await db_session.refresh(payment)
    assert payment.status != "COMPLETED"


@pytest.mark.parametrize(
    "damage", ["order_id", "merchant", "custom_id", "reference_id", "amount"]
)
async def test_preflight_verifies_order_identity_before_charge(
    service, fake_paypal, db_session, damage
):
    payment = await created(service, fake_paypal, db_session)
    body = identified(order_detail_response(status="APPROVED"), payment)
    unit = body["purchase_units"][0]
    if damage == "order_id":
        body["id"] = "WRONGORDER12345"
    elif damage == "merchant":
        unit["payee"]["merchant_id"] = "OTHER"
    elif damage == "custom_id":
        unit["custom_id"] = "OTHER"
    elif damage == "reference_id":
        unit["reference_id"] = "OTHER"
    else:
        unit["amount"]["value"] = "0.01"
    fake_paypal.set("GET", order_path(), body)
    fake_paypal.set("POST", capture_path(), identified(capture_response(), payment))
    with pytest.raises(RescuePayError):
        await service.capture_order(SAMPLE_ORDER_ID)
    assert fake_paypal.requests_to("POST", capture_path()) == []


async def test_unknown_capture_is_not_reset_to_approved(
    service, fake_paypal, db_session
):
    payment = await created(service, fake_paypal, db_session)
    lookups = 0

    def lookup():
        nonlocal lookups
        lookups += 1
        if lookups == 1:
            return identified(order_detail_response(status="APPROVED"), payment)
        raise httpx.ReadTimeout("synthetic reconciliation outage")

    fake_paypal.set("GET", order_path(), lookup)
    fake_paypal.set(
        "POST", capture_path(), httpx.ReadTimeout("synthetic capture timeout")
    )
    with pytest.raises(RescuePayError):
        await service.capture_order(SAMPLE_ORDER_ID)
    await db_session.refresh(payment)
    assert payment.status == "CAPTURE_UNCERTAIN"


async def test_stuck_capture_can_reconcile_without_another_charge(
    service, fake_paypal, db_session
):
    payment = await created(service, fake_paypal, db_session)
    assert await PaymentRepository(db_session).try_begin_capture(payment.id)
    await db_session.refresh(payment)
    payment.updated_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.commit()
    body = identified(order_detail_response(status="COMPLETED"), payment)
    body["purchase_units"][0]["payments"] = capture_response()["purchase_units"][0][
        "payments"
    ]
    fake_paypal.set("GET", order_path(), body)
    status = await service.get_order(SAMPLE_ORDER_ID)
    assert status.status == "COMPLETED"
    assert fake_paypal.requests_to("POST", capture_path()) == []


async def test_no_payable_source_does_not_trust_the_client(
    db_session, paypal_client, settings, fake_paypal
):
    unconfigured = PaymentService(db_session, paypal_client, settings)
    fake_paypal.set("POST", ORDERS_PATH, created_order_response())
    with pytest.raises(RescuePayError):
        await unconfigured.create_order(
            CreateOrderRequest(reference_id="UNTRUSTED", currency="USD", amount="0.01")
        )
    assert fake_paypal.requests == []
    assert (await db_session.execute(select(Payment))).scalars().all() == []


@pytest.mark.parametrize(
    "overrides", [{"amount": "0.01"}, {"currency": "EUR"}, {"reference_id": "UNKNOWN"}]
)
async def test_authoritative_source_rejects_tampered_payables(
    service, fake_paypal, db_session, overrides
):
    request = {
        "reference_id": "RESCUE-1001",
        "currency": "USD",
        "amount": "25.00",
        **overrides,
    }
    with pytest.raises(RescuePayError):
        await service.create_order(CreateOrderRequest(**request))
    assert fake_paypal.requests == []
    assert (await db_session.execute(select(Payment))).scalars().all() == []


def test_io_boundary_rejects_bypassed_settings_and_live_injected_client(settings):
    from app.integrations.paypal import PayPalClient

    with pytest.raises(ValueError):
        PayPalClient(settings.model_copy(update={"PAYPAL_MODE": "live"}))
    client = httpx.AsyncClient(
        base_url="https://api-m.paypal.com",
        transport=httpx.MockTransport(lambda r: httpx.Response(200)),
    )
    with pytest.raises(ValueError):
        PayPalClient(settings, http_client=client)


async def test_api_redirect_does_not_leave_sandbox(settings):
    from app.integrations.paypal import PayPalClient

    requests = []

    def redirect(request):
        requests.append(request)
        return httpx.Response(
            302, headers={"Location": "https://api-m.paypal.com/stolen"}
        )

    async with httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL,
        transport=httpx.MockTransport(redirect),
        follow_redirects=True,
    ) as http:
        client = PayPalClient(settings, http_client=http)
        with pytest.raises(RescuePayError):
            await client.get_access_token()
    assert len(requests) == 1
    assert requests[0].url.host == "api-m.sandbox.paypal.com"


async def test_creation_replay_survives_new_session_and_never_reposts(
    database, settings, fake_paypal
):
    key = str(uuid4())
    request = CreateOrderRequest(
        reference_id="RESCUE-1001", currency="USD", amount="25.00"
    )
    client = make_paypal_client(settings, fake_paypal)
    fake_paypal.set("POST", ORDERS_PATH, created_order_response())
    async with database.session_factory() as session:
        first = await PaymentService(
            session, client, settings, payable_source=TEST_PAYABLES
        ).create_order(request, idempotency_key=key)
    async with database.session_factory() as session:
        service = PaymentService(
            session, client, settings, payable_source=TEST_PAYABLES
        )
        replay = await service.create_order(request, idempotency_key=key)
        assert (replay.payment_id, replay.order_id, replay.request_id) == (
            first.payment_id,
            first.order_id,
            first.request_id,
        )
        assert len((await session.execute(select(Payment))).scalars().all()) == 1
        with pytest.raises(RescuePayError, match="different payment details"):
            await service.create_order(
                request.model_copy(update={"description": "changed"}),
                idempotency_key=key,
            )
    assert len(fake_paypal.requests_to("POST", ORDERS_PATH)) == 1


async def test_creation_timeout_replay_cannot_create_a_second_order(
    service, fake_paypal, db_session
):
    key = str(uuid4())
    request = CreateOrderRequest(
        reference_id="RESCUE-1001", currency="USD", amount="25.00"
    )
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.ReadTimeout("synthetic creation timeout")
    )
    with pytest.raises(RescuePayError):
        await service.create_order(request, idempotency_key=key)
    with pytest.raises(RescuePayError, match="creation is unresolved"):
        await service.create_order(request, idempotency_key=key)
    assert len(fake_paypal.requests_to("POST", ORDERS_PATH)) == 1
    rows = (await db_session.execute(select(Payment))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "CREATION_UNCERTAIN"


async def test_concurrent_creation_uses_one_persisted_operation(
    database, settings, fake_paypal
):
    key = str(uuid4())
    request = CreateOrderRequest(
        reference_id="RESCUE-1001", currency="USD", amount="25.00"
    )
    fake_paypal.set("POST", ORDERS_PATH, created_order_response())
    client = make_paypal_client(settings, fake_paypal)

    async def create_once():
        async with database.session_factory() as session:
            try:
                result = await PaymentService(
                    session, client, settings, payable_source=TEST_PAYABLES
                ).create_order(request, idempotency_key=key)
                return result.payment_id
            except RescuePayError as error:
                assert error.error_code == "ORDER_CREATION_UNCERTAIN"
                return None

    results = await asyncio.gather(*(create_once() for _ in range(5)))
    assert len({result for result in results if result}) == 1
    assert len(fake_paypal.requests_to("POST", ORDERS_PATH)) == 1
    async with database.session_factory() as session:
        assert len((await session.execute(select(Payment))).scalars().all()) == 1


async def test_expired_capture_without_evidence_stays_uncertain(
    service, fake_paypal, db_session
):
    payment = await created(service, fake_paypal, db_session)
    assert await PaymentRepository(db_session).try_begin_capture(payment.id)
    await db_session.refresh(payment)
    payment.updated_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.commit()
    fake_paypal.set(
        "GET",
        order_path(),
        identified(order_detail_response(status="APPROVED"), payment),
    )
    for _ in range(2):
        with pytest.raises(CaptureUncertainError):
            await service.capture_order(SAMPLE_ORDER_ID)
    assert (await service.get_order(SAMPLE_ORDER_ID)).status == "CAPTURE_UNCERTAIN"
    assert fake_paypal.requests_to("POST", capture_path()) == []


async def test_active_capture_is_not_recovered_early(service, fake_paypal, db_session):
    payment = await created(service, fake_paypal, db_session)
    assert await PaymentRepository(db_session).try_begin_capture(payment.id)
    await db_session.commit()
    with pytest.raises(CaptureInProgressError):
        await service.capture_order(SAMPLE_ORDER_ID)
    status = await service.get_order(SAMPLE_ORDER_ID)
    assert status.status == "CAPTURING"
    assert status.provider_refreshed is False
    assert fake_paypal.requests_to("GET", order_path()) == []


async def test_stale_lookup_cannot_unlock_a_concurrent_capture(
    database, settings, fake_paypal
):
    client = make_paypal_client(settings, fake_paypal)
    async with database.session_factory() as session:
        payment = await created(
            PaymentService(session, client, settings, payable_source=TEST_PAYABLES),
            fake_paypal,
            session,
        )
    lookup_started = asyncio.Event()
    release_lookup = asyncio.Event()
    capture_started = asyncio.Event()
    release_capture = asyncio.Event()
    first_lookup = True

    async def handler(request):
        nonlocal first_lookup
        if request.method == "GET" and request.url.path == order_path():
            if first_lookup:
                first_lookup = False
                lookup_started.set()
                await release_lookup.wait()
            return httpx.Response(
                200, json=identified(order_detail_response(status="APPROVED"), payment)
            )
        if request.method == "POST" and request.url.path == capture_path():
            fake_paypal.requests.append(request)
            capture_started.set()
            await release_capture.wait()
            return httpx.Response(201, json=capture_response(payment_id=payment.id))
        return fake_paypal.handler(request)

    from app.integrations.paypal import PayPalClient

    async with httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL, transport=httpx.MockTransport(handler)
    ) as http:
        shared = PayPalClient(settings, http_client=http)

        async def operation(capture):
            async with database.session_factory() as session:
                service = PaymentService(
                    session, shared, settings, payable_source=TEST_PAYABLES
                )
                return await (
                    service.capture_order(SAMPLE_ORDER_ID)
                    if capture
                    else service.get_order(SAMPLE_ORDER_ID)
                )

        lookup = asyncio.create_task(operation(False))
        try:
            await asyncio.wait_for(lookup_started.wait(), 5)
            capture = asyncio.create_task(operation(True))
            try:
                await asyncio.wait_for(capture_started.wait(), 5)
                release_lookup.set()
                assert (await lookup).status == "CAPTURING"
                with pytest.raises(CaptureInProgressError):
                    await operation(True)
            finally:
                release_capture.set()
            assert (await capture).status == "COMPLETED"
        finally:
            release_lookup.set()
            release_capture.set()
    assert len(fake_paypal.requests_to("POST", capture_path())) == 1


async def test_pending_capture_seen_by_lookup_from_created_is_valid(
    service, fake_paypal, db_session
):
    payment = await created(service, fake_paypal, db_session)
    body = identified(order_detail_response(status="COMPLETED"), payment)
    body["purchase_units"][0]["payments"] = capture_response(capture_status="PENDING")[
        "purchase_units"
    ][0]["payments"]
    fake_paypal.set("GET", order_path(), body)
    first = await service.get_order(SAMPLE_ORDER_ID)
    second = await service.get_order(SAMPLE_ORDER_ID)
    assert first.status == second.status == "CAPTURE_PENDING"
    assert first.capture_id is not None
    assert fake_paypal.requests_to("POST", capture_path()) == []


async def test_duplicate_provider_capture_id_is_quarantined(
    service, fake_paypal, db_session
):
    first = await created(service, fake_paypal, db_session)
    fake_paypal.set(
        "GET", order_path(), identified(order_detail_response(status="APPROVED"), first)
    )
    fake_paypal.set("POST", capture_path(), identified(capture_response(), first))
    assert (await service.capture_order(SAMPLE_ORDER_ID)).status == "COMPLETED"
    other_order = "OTHERORDER12345"
    fake_paypal.set("POST", ORDERS_PATH, created_order_response(other_order))
    response = await service.create_order(
        CreateOrderRequest(reference_id="RESCUE-1001", currency="USD", amount="25.00")
    )
    other = await db_session.get(Payment, response.payment_id)
    fake_paypal.set(
        "GET",
        order_path(other_order),
        identified(
            order_detail_response(order_id=other_order, status="APPROVED"), other
        ),
    )
    fake_paypal.set(
        "POST",
        capture_path(other_order),
        identified(capture_response(order_id=other_order), other),
    )
    result = await service.capture_order(other_order)
    assert result.status == "CAPTURE_UNCERTAIN"
    assert result.capture_id is None
    await db_session.refresh(first)
    assert first.status == "COMPLETED"


async def test_expired_owner_cannot_dispatch_capture_after_recovery(
    database, settings, fake_paypal
):
    client = make_paypal_client(settings, fake_paypal)
    async with database.session_factory() as session:
        payment = await created(
            PaymentService(session, client, settings, payable_source=TEST_PAYABLES),
            fake_paypal,
            session,
        )
    started = asyncio.Event()
    release = asyncio.Event()
    first_lookup = True

    async def handler(request):
        nonlocal first_lookup
        if request.method == "GET":
            if first_lookup:
                first_lookup = False
                started.set()
                await release.wait()
            return httpx.Response(
                200, json=identified(order_detail_response(status="APPROVED"), payment)
            )
        return fake_paypal.handler(request)

    from app.integrations.paypal import PayPalClient

    async with httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL, transport=httpx.MockTransport(handler)
    ) as http:
        shared = PayPalClient(settings, http_client=http)

        async def original_capture():
            async with database.session_factory() as session:
                return await PaymentService(
                    session, shared, settings, payable_source=TEST_PAYABLES
                ).capture_order(SAMPLE_ORDER_ID)

        pending = asyncio.create_task(original_capture())
        try:
            await asyncio.wait_for(started.wait(), 5)
            async with database.session_factory() as session:
                repo = PaymentRepository(session)
                locked = await repo.get_by_paypal_order_id(SAMPLE_ORDER_ID)
                locked.updated_at = datetime.now(UTC) - timedelta(hours=1)
                await session.commit()
                status = await PaymentService(
                    session, shared, settings, payable_source=TEST_PAYABLES
                ).get_order(SAMPLE_ORDER_ID)
                assert status.status == "CAPTURE_UNCERTAIN"
        finally:
            release.set()
        with pytest.raises(CaptureUncertainError):
            await pending
    assert fake_paypal.requests_to("POST", capture_path()) == []


@pytest.mark.parametrize(
    "href",
    [
        "https://www.paypal.com/checkoutnow?token=5O190127TN364715T",
        "https://www.sandbox.paypal.com.evil.test/checkoutnow?token=5O190127TN364715T",
        "http://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T",
        "https://www.sandbox.paypal.com/checkoutnow?token=DIFFERENT",
    ],
)
async def test_creation_never_returns_an_untrusted_approval_redirect(
    service, fake_paypal, db_session, href
):
    body = created_order_response()
    body["links"][1]["href"] = href
    fake_paypal.set("POST", ORDERS_PATH, body)
    with pytest.raises(RescuePayError):
        await service.create_order(
            CreateOrderRequest(
                reference_id="RESCUE-1001", currency="USD", amount="25.00"
            )
        )
    row = (await db_session.execute(select(Payment))).scalar_one()
    assert row.status == "CREATION_UNCERTAIN"
    assert row.approval_url is None


async def test_status_lookup_cannot_bypass_unconfigured_price_authority(
    service, fake_paypal, db_session, paypal_client, settings
):
    payment = await created(service, fake_paypal, db_session)
    body = identified(order_detail_response(status="COMPLETED"), payment)
    body["purchase_units"][0]["payments"] = capture_response()["purchase_units"][0][
        "payments"
    ]
    fake_paypal.set("GET", order_path(), body)
    unconfigured = PaymentService(db_session, paypal_client, settings)
    result = await unconfigured.get_order(SAMPLE_ORDER_ID)
    assert result.status == "CAPTURE_UNCERTAIN"
    assert result.provider_refreshed is False
    assert (await service.get_order(SAMPLE_ORDER_ID)).status == "COMPLETED"
    assert fake_paypal.requests_to("POST", capture_path()) == []
