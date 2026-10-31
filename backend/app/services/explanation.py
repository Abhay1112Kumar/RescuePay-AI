"""Read-only stored-evidence projection. No PayPal, credentials or payment writes."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import OrderNotFoundError
from app.integrations.gemini import GeminiUnavailable
from app.models.payment import Payment, PaymentEvent
from app.schemas.evidence import (
    EvidenceEvent,
    EvidenceFact,
    EvidenceResponse,
    ExplanationDiagnostic,
    ExplanationPlan,
    PaymentEvidence,
)
from app.schemas.payment import MoneyAmount
from app.services.payment_state import PaymentStatus

# An allowlist, never event.detail, last_error, descriptions or arbitrary strings.
EVENT_CODES = {
    "payment.created": "RECORD_CREATED",
    "paypal.order.created": "ORDER_CREATED",
    "paypal.order.approved": "APPROVAL_OBSERVED",
    "payment.capture.started": "CAPTURE_STARTED",
    "paypal.capture.completed": "CAPTURE_COMPLETED",
    "paypal.capture.pending": "CAPTURE_PENDING",
    "paypal.capture.outcome_uncertain": "CAPTURE_UNCERTAIN",
    "payment.capture.lease_expired": "CAPTURE_LEASE_EXPIRED",
    "payment.verification_upgrade": "LEGACY_REVERIFICATION_REQUIRED",
}


class ExplanationProvider(Protocol):
    async def explain(self, evidence: PaymentEvidence) -> object:
        """Return untrusted structured fact/action selections, never payment commands."""
        ...


def utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def explain_payment(
    session: AsyncSession,
    order_id: str,
    provider: ExplanationProvider | None = None,
    *,
    timeout: float = 2.0,
    owner_id: str | None = None,
) -> EvidenceResponse:
    # Single SELECT snapshot binds record and audit evidence. Bound the event tail.
    query = (
        select(Payment, PaymentEvent)
        .outerjoin(PaymentEvent, PaymentEvent.payment_id == Payment.id)
        .where(Payment.paypal_order_id == order_id)
        .order_by(PaymentEvent.id.desc())
    )
    if isinstance(owner_id, str):
        query = query.where(
            Payment.reference_id.startswith("synthetic")
            | Payment.reference_id.startswith("demo-")
        )
    query = query.limit(51)
    rows = (await session.execute(query)).all()
    if not rows:
        raise OrderNotFoundError()
    payment = rows[0][0]
    state = PaymentStatus(payment.status)
    uncertain = state in {
        PaymentStatus.PENDING,
        PaymentStatus.CREATION_UNCERTAIN,
        PaymentStatus.CAPTURING,
        PaymentStatus.CAPTURE_UNCERTAIN,
    }
    facts = [
        EvidenceFact(
            code="STORED_STATE", text=f"Stored backend payment state: {state.value}."
        ),
        EvidenceFact(
            code="FRESHNESS_UNKNOWN",
            text="Current provider state was not checked. This is stored evidence, not a live payment confirmation.",
        ),
        EvidenceFact(
            code="CANCEL_NOT_VOID",
            text="Browser cancellation does not establish provider VOIDED status.",
        ),
    ]
    if state == PaymentStatus.COMPLETED and payment.paypal_capture_id:
        facts.append(
            EvidenceFact(
                code="RECORDED_CAPTURE",
                text="The backend previously recorded a verified completed capture. Later refunds or disputes are not checked here.",
            )
        )
    elif state == PaymentStatus.COMPLETED:
        uncertain = True
        facts.append(
            EvidenceFact(
                code="MISSING_CAPTURE",
                text="The stored completed state lacks capture identity; manual reconciliation is required.",
            )
        )
    else:
        facts.append(
            EvidenceFact(
                code="NOT_CONFIRMED_PAID",
                text="This evidence does not establish a completed payment.",
            )
        )
    actions = (
        ("MANUAL_RECONCILIATION", "CHECK_STATUS")
        if uncertain
        else ("WAIT", "CHECK_STATUS")
        if state == PaymentStatus.CAPTURE_PENDING
        else ("REVIEW_RECORD",)
        if state
        in {PaymentStatus.COMPLETED, PaymentStatus.FAILED, PaymentStatus.VOIDED}
        else ("CHECK_STATUS",)
    )
    events = tuple(
        EvidenceEvent(
            code=EVENT_CODES[event.event_type],
            state=PaymentStatus(event.to_status)
            if event.to_status in PaymentStatus._value2member_map_
            else None,
            recorded_at=utc(event.created_at),
        )
        for _, event in reversed(rows[:50])
        if event is not None and event.event_type in EVENT_CODES
    )
    evidence = PaymentEvidence(
        state=state,
        amount=MoneyAmount(
            currency_code=payment.currency,
            value=f"{Decimal(payment.amount_minor) / 100:.2f}",
        ),
        observed_at=datetime.now(UTC),
        record_updated_at=utc(payment.updated_at),
        uncertain=uncertain,
        events_truncated=len(rows) > 50,
        events=events,
        facts=tuple(facts),
        safe_actions=actions,
    )
    if provider is None:
        return EvidenceResponse(
            evidence=evidence,
            ai_status="unavailable",
            ai_reason="provider_not_configured",
        )
    try:
        # Pass a detached copy: model implementations cannot mutate displayed facts.
        raw = await asyncio.wait_for(
            provider.explain(evidence.model_copy(deep=True)), timeout=timeout
        )
        plan = ExplanationPlan.model_validate(raw)
        if (
            len(set(plan.fact_codes)) != len(plan.fact_codes)
            or not set(plan.fact_codes) <= {fact.code for fact in evidence.facts}
            or len(set(plan.action_codes)) != len(plan.action_codes)
            or not set(plan.action_codes) <= set(evidence.safe_actions)
        ):
            raise ValueError("Unsupported model selection")
    except Exception as exc:
        diagnostic = (
            exc.diagnostic
            if isinstance(exc, GeminiUnavailable)
            else ExplanationDiagnostic(
                category="timeout"
                if isinstance(exc, TimeoutError)
                else "schema_mismatch",
                stage="service",
            )
        )
        return EvidenceResponse(
            evidence=evidence,
            ai_status="unavailable",
            ai_reason="invalid_or_unavailable_output",
            ai_diagnostic=diagnostic,
        )
    return EvidenceResponse(
        evidence=evidence, ai_status="available", model_selection=plan
    )
