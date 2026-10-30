"""Data access for Payment and PaymentEvent.

The repository does not commit. The service owns transaction boundaries so a
state change and its audit event are always written together.
"""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment, PaymentEvent
from app.services.payment_state import (
    CAPTURABLE_STATES,
    PaymentStatus,
    assert_transition,
)


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    async def get(self, payment_id: str) -> Payment | None:
        return await self._session.get(Payment, payment_id)

    async def get_by_paypal_order_id(self, order_id: str) -> Payment | None:
        result = await self._session.execute(
            select(Payment).where(Payment.paypal_order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def list_events(self, payment_id: str) -> list[PaymentEvent]:
        result = await self._session.execute(
            select(PaymentEvent)
            .where(PaymentEvent.payment_id == payment_id)
            .order_by(PaymentEvent.id)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------ #
    # Writes (no commit here)
    # ------------------------------------------------------------------ #
    async def add(
        self, payment: Payment, *, event_type: str, detail: str | None = None
    ) -> Payment:
        self._session.add(payment)
        await self._session.flush()
        self.record_event(
            payment,
            event_type,
            from_status=None,
            to_status=payment.status,
            detail=detail,
        )
        return payment

    def record_event(
        self,
        payment: Payment,
        event_type: str,
        *,
        from_status: str | None,
        to_status: str | None,
        detail: str | None = None,
        paypal_debug_id: str | None = None,
    ) -> PaymentEvent:
        event = PaymentEvent(
            payment_id=payment.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            detail=detail,
            paypal_debug_id=paypal_debug_id,
        )
        self._session.add(event)
        return event

    def transition(
        self,
        payment: Payment,
        target: PaymentStatus,
        *,
        event_type: str,
        detail: str | None = None,
        paypal_debug_id: str | None = None,
    ) -> None:
        """Move ``payment`` to ``target`` after validating the state machine."""
        current = PaymentStatus(payment.status)
        assert_transition(current, target)
        payment.status = target.value
        payment.updated_at = datetime.now(UTC)
        if detail is not None and target is PaymentStatus.FAILED:
            payment.last_error = detail[:255]
        self.record_event(
            payment,
            event_type,
            from_status=current.value,
            to_status=target.value,
            detail=detail,
            paypal_debug_id=paypal_debug_id,
        )

    async def try_begin_capture(self, payment_id: str) -> bool:
        """Atomically move a capturable payment to CAPTURING.

        Uses a conditional UPDATE so two concurrent capture requests (even from
        different processes) cannot both pass. Returns True if this caller won.
        """
        result = await self._session.execute(
            update(Payment)
            .where(
                Payment.id == payment_id,
                Payment.status.in_([s.value for s in CAPTURABLE_STATES]),
            )
            .values(status=PaymentStatus.CAPTURING.value, updated_at=datetime.now(UTC))
        )
        return (result.rowcount or 0) == 1

    async def refresh(self, payment: Payment) -> None:
        await self._session.refresh(payment)
