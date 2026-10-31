"""Synthetic evidence only. No provider/network operation is used by this API."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.evidence import require_local_evidence
from app.core.config import get_settings
from app.main import app
from app.models.payment import Payment, PaymentEvent
from app.services.explanation import explain_payment
from tests.conftest import SAMPLE_ORDER_ID, make_settings


async def seed(session, state="CAPTURE_UNCERTAIN"):
    payment = Payment(
        reference_id="private-reference",
        description="buyer@example.test SECRET",
        currency="USD",
        amount_minor=100,
        status=state,
        paypal_order_id=SAMPLE_ORDER_ID,
        paypal_capture_id="CAPTURESECRET" if state == "COMPLETED" else None,
        last_error="Bearer SECRET",
    )
    session.add(payment)
    await session.flush()
    session.add_all(
        [
            PaymentEvent(
                payment_id=payment.id,
                event_type="paypal.capture.outcome_uncertain",
                to_status=state,
                detail="buyer@example.test SECRET",
                paypal_debug_id="DEBUGSECRET",
                created_at=datetime.now(UTC) - timedelta(days=3),
            ),
            PaymentEvent(
                payment_id=payment.id,
                event_type="PRIVATE_SECRET_EVENT",
                detail="SECRET",
            ),
        ]
    )
    await session.commit()
    return payment


async def test_projection_redacts_and_preserves_state(db_session):
    payment = await seed(db_session)
    before = (payment.status, payment.version, payment.last_error)
    result = await explain_payment(db_session, SAMPLE_ORDER_ID)
    raw = result.model_dump_json()
    for secret in [
        "SECRET",
        "buyer@",
        payment.id,
        SAMPLE_ORDER_ID,
        "private-reference",
        "DEBUGSECRET",
    ]:
        assert secret not in raw
    assert len(result.evidence.events) == 1
    assert result.evidence.uncertain
    assert result.evidence.provider_freshness == "not_checked"
    assert not result.evidence.current_provider_state_verified
    assert result.ai_status == "unavailable"
    assert "MANUAL_RECONCILIATION" in result.evidence.safe_actions
    await db_session.refresh(payment)
    assert (payment.status, payment.version, payment.last_error) == before


@pytest.mark.parametrize(
    "state",
    [
        "CREATED",
        "CAPTURING",
        "CAPTURE_PENDING",
        "COMPLETED",
        "FAILED",
        "VOIDED",
        "CREATION_UNCERTAIN",
    ],
)
async def test_stored_states_never_claim_freshness(db_session, state):
    await seed(db_session, state)
    result = await explain_payment(db_session, SAMPLE_ORDER_ID)
    assert result.evidence.state == state
    assert result.evidence.current_provider_state_verified is False
    assert "CANCEL_NOT_VOID" in [f.code for f in result.evidence.facts]
    assert not {"CAPTURE", "REFUND", "NEW_CHECKOUT"} & set(result.evidence.safe_actions)
    assert ("RECORDED_CAPTURE" in [f.code for f in result.evidence.facts]) == (
        state == "COMPLETED"
    )


@pytest.mark.parametrize(
    "output",
    [
        {"fact_codes": ["PAID"], "action_codes": []},
        {"fact_codes": ["STORED_STATE"], "action_codes": ["CAPTURE"]},
        {"fact_codes": ["STORED_STATE"], "action_codes": ["REVIEW_RECORD"]},
        {
            "fact_codes": ["STORED_STATE"],
            "action_codes": [],
            "summary": "Payment succeeded",
        },
        {"fact_codes": ["STORED_STATE", "STORED_STATE"], "action_codes": []},
        {"fact_codes": [], "action_codes": []},
        "Bearer SECRET",
    ],
)
async def test_invalid_model_output_is_rejected_without_mutation(db_session, output):
    payment = await seed(db_session)

    class FakeProvider:
        async def explain(self, evidence):
            assert "SECRET" not in evidence.model_dump_json()
            return output

    result = await explain_payment(db_session, SAMPLE_ORDER_ID, FakeProvider())
    assert result.ai_status == "unavailable"
    assert result.ai_reason == "invalid_or_unavailable_output"
    assert result.model_selection is None
    assert "SECRET" not in result.model_dump_json()
    await db_session.refresh(payment)
    assert payment.status == "CAPTURE_UNCERTAIN"


async def test_structured_selection_is_grounded_and_provider_failure_is_sanitized(
    db_session,
):
    await seed(db_session)

    class FakeProvider:
        async def explain(self, evidence):
            return {"fact_codes": ["STORED_STATE"], "action_codes": ["CHECK_STATUS"]}

    result = await explain_payment(db_session, SAMPLE_ORDER_ID, FakeProvider())
    assert result.ai_status == "available"

    class Broken:
        async def explain(self, evidence):
            raise RuntimeError("SECRET")

    result = await explain_payment(db_session, SAMPLE_ORDER_ID, Broken())
    assert (
        result.ai_status == "unavailable" and "SECRET" not in result.model_dump_json()
    )


def request(host="localhost", client="127.0.0.1", extra=()):
    return Request(
        {
            "type": "http",
            "scheme": "http",
            "path": "/",
            "server": (host, 8000),
            "client": (client, 123),
            "headers": [(b"host", host.encode()), *extra],
        }
    )


@pytest.mark.parametrize(
    "req,enabled,env",
    [
        (request(), False, "development"),
        (request(client="10.0.0.2"), True, "development"),
        (request(host="public.example"), True, "development"),
        (request(extra=((b"x-forwarded-for", b"127.0.0.1"),)), True, "development"),
        (request(extra=((b"origin", b"https://public.example"),)), True, "development"),
        (request(), True, "production"),
    ],
)
def test_local_api_gate_rejects_unsafe_exposure(req, enabled, env):
    with pytest.raises(HTTPException) as exc:
        require_local_evidence(
            req, make_settings(LOCAL_EVIDENCE_ENABLED=enabled, APP_ENV=env)
        )
    assert exc.value.status_code == 404


async def test_actual_readonly_route_needs_no_paypal_dependency(database):
    async with database.session_factory() as session:
        await seed(session)
    app.state.database = database
    app.dependency_overrides[get_settings] = lambda: make_settings(
        APP_ENV="development", LOCAL_EVIDENCE_ENABLED=True
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
        base_url="http://localhost",
    ) as client:
        response = await client.get(
            f"/api/v1/payments/orders/{SAMPLE_ORDER_ID}/evidence"
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["ai_status"] == "unavailable"
        assert "SECRET" not in response.text
        missing = await client.get("/api/v1/payments/orders/UNKNOWNORDER123/evidence")
        assert missing.status_code == 404


async def test_bounded_event_tail_and_missing_capture_do_not_invent_success(db_session):
    payment = await seed(db_session, "COMPLETED")
    payment.paypal_capture_id = None
    for _ in range(55):
        db_session.add(
            PaymentEvent(
                payment_id=payment.id, event_type="payment.created", to_status="CREATED"
            )
        )
    await db_session.commit()
    result = await explain_payment(db_session, SAMPLE_ORDER_ID)
    assert result.evidence.events_truncated
    assert len(result.evidence.events) == 50
    assert result.evidence.uncertain
    assert "MISSING_CAPTURE" in [f.code for f in result.evidence.facts]
    assert "MANUAL_RECONCILIATION" in result.evidence.safe_actions
