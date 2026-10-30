"""Persistent payment entities.

``Payment`` is the backend's trusted record of what is being paid for. Its
``amount_minor`` is the authority that PayPal's figures are checked against
before capture. ``PaymentEvent`` is an append-only audit trail of every state
transition and notable provider interaction.

Money is stored as integer minor units (cents) to avoid floating point and to
keep SQLite and PostgreSQL behaviour identical. All supported currencies use a
two-digit exponent; the service layer enforces that.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.services.payment_state import PaymentStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reference_id: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(127))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PaymentStatus.PENDING.value
    )

    # Provider identifiers, kept separate from our own primary key.
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    paypal_capture_id: Mapped[str | None] = mapped_column(String(64), unique=True)

    # Idempotency keys sent as PayPal-Request-Id. Stable per payment so a retried
    # create or capture is de-duplicated by PayPal instead of duplicated.
    create_request_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, default=new_id
    )
    capture_request_id: Mapped[str | None] = mapped_column(String(36), unique=True)

    # Short, sanitized description of the last failure (never raw provider bodies).
    last_error: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    events: Mapped[list["PaymentEvent"]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
        order_by="PaymentEvent.id",
    )

    __table_args__ = (
        Index("ix_payments_reference_id", "reference_id"),
        Index("ix_payments_status", "status"),
    )


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(Text)
    paypal_debug_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    payment: Mapped[Payment] = relationship(back_populates="events")

    __table_args__ = (Index("ix_payment_events_payment_id", "payment_id"),)
