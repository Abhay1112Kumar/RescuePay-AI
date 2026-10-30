"""Payment domain business logic.

The backend's ``Payment`` row is the trusted record. The flow is:

1. ``create_order``: persist a PENDING record first (so the amount becomes a
   backend fact), then create the PayPal order with a stable request id, then
   mark CREATED. A provider failure marks FAILED with a sanitized reason.
2. ``get_order``: return the local record, refreshed from PayPal when the
   payment is still in flight (APPROVED / VOIDED / out-of-band COMPLETED).
3. ``capture_order``: take an atomic CAPTURING lock, re-read the order from
   PayPal, verify amount + currency against our record, capture with a stable
   request id, and only mark COMPLETED after PayPal confirms. Uncertain
   outcomes (timeouts, 5xx) are resolved by re-reading the order, never by a
   blind retry. Repeated capture calls on a COMPLETED payment return the same
   result instead of charging twice.

Every state change is written together with an audit event in one transaction.
"""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    AmountMismatchError,
    CaptureInProgressError,
    OrderNotApprovedError,
    OrderNotFoundError,
    PaymentDeclinedError,
    PaymentStateError,
    PaymentValidationError,
    PayPalAPIError,
)
from app.integrations.paypal import PayPalClient
from app.models.payment import Payment
from app.repositories.payment_repository import PaymentRepository
from app.schemas.payment import (
    CaptureResponse,
    CreateOrderRequest,
    MoneyAmount,
    OrderLink,
    OrderResponse,
    OrderStatusResponse,
)
from app.services.payment_state import (
    CAPTURABLE_STATES,
    PaymentStatus,
    is_terminal,
)

logger = logging.getLogger(__name__)

# PayPal returns the buyer redirect as rel="approve" (application_context flow) or
# rel="payer-action" (payment_source flow). Accept either.
_APPROVAL_RELS = ("approve", "payer-action")

# PayPal 4xx capture issues that mean "buyer must act again", not "payment failed".
_NOT_APPROVED_ISSUES = frozenset({"ORDER_NOT_APPROVED", "PAYER_ACTION_REQUIRED"})
_DECLINED_ISSUES = frozenset({"INSTRUMENT_DECLINED"})
_ALREADY_CAPTURED_ISSUES = frozenset({"ORDER_ALREADY_CAPTURED"})

_MINOR_UNIT = Decimal("0.01")


# ---------------------------------------------------------------------- #
# Money helpers
# ---------------------------------------------------------------------- #
def format_amount(amount: Decimal) -> str:
    """Render a Decimal as PayPal expects: two decimal places, no exponent."""
    return f"{amount.quantize(_MINOR_UNIT):f}"


def to_minor(amount: Decimal) -> int:
    """Decimal major units -> integer minor units (cents)."""
    return int((amount.quantize(_MINOR_UNIT) / _MINOR_UNIT).to_integral_value())


def from_minor(amount_minor: int) -> Decimal:
    """Integer minor units -> Decimal major units."""
    return (Decimal(amount_minor) * _MINOR_UNIT).quantize(_MINOR_UNIT)


def _as_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo; our timestamps are always UTC, so restore it."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _money(payment: Payment) -> MoneyAmount:
    return MoneyAmount(
        currency_code=payment.currency,
        value=format_amount(from_minor(payment.amount_minor)),
    )


def _first_capture(order_or_capture_body: dict[str, Any]) -> dict[str, Any] | None:
    """Locate ``purchase_units[0].payments.captures[0]`` in a PayPal body."""
    units = order_or_capture_body.get("purchase_units")
    if not isinstance(units, list) or not units or not isinstance(units[0], dict):
        return None
    payments = units[0].get("payments")
    if not isinstance(payments, dict):
        return None
    captures = payments.get("captures")
    if (
        not isinstance(captures, list)
        or not captures
        or not isinstance(captures[0], dict)
    ):
        return None
    return captures[0]


def _order_amount(order: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(currency_code, value)`` from ``purchase_units[0].amount``."""
    units = order.get("purchase_units")
    if not isinstance(units, list) or not units or not isinstance(units[0], dict):
        return None
    amount = units[0].get("amount")
    if not isinstance(amount, dict):
        return None
    code, value = amount.get("currency_code"), amount.get("value")
    if not isinstance(code, str) or not isinstance(value, str):
        return None
    return code, value


class PaymentService:
    """Service handling payment operations, lifecycle, and transaction workflows."""

    def __init__(
        self,
        session: AsyncSession,
        paypal_client: PayPalClient,
        settings: Settings,
    ) -> None:
        self._session = session
        self._repo = PaymentRepository(session)
        self._paypal = paypal_client
        self._settings = settings

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def _validate_business_rules(self, request: CreateOrderRequest) -> None:
        if request.currency not in self._settings.allowed_currencies:
            allowed = ", ".join(sorted(self._settings.allowed_currencies))
            raise PaymentValidationError(
                f"Currency '{request.currency}' is not supported. Allowed: {allowed}."
            )
        if request.amount > self._settings.PAYMENT_MAX_AMOUNT:
            raise PaymentValidationError(
                "Amount exceeds the maximum allowed of "
                f"{format_amount(self._settings.PAYMENT_MAX_AMOUNT)} {request.currency}."
            )

    def _verify_order_matches_record(
        self, payment: Payment, order: dict[str, Any]
    ) -> None:
        """Refuse to proceed if PayPal's order amount/currency differ from our record."""
        found = _order_amount(order)
        expected = (payment.currency, format_amount(from_minor(payment.amount_minor)))
        if found is None or found != expected:
            logger.error(
                "payment.capture.amount_mismatch",
                extra={
                    "payment_id": payment.id,
                    "order_id": payment.paypal_order_id,
                    "expected_currency": expected[0],
                    "expected_value": expected[1],
                    "paypal_currency": found[0] if found else None,
                    "paypal_value": found[1] if found else None,
                },
            )
            raise AmountMismatchError()

    # ------------------------------------------------------------------ #
    # Order creation
    # ------------------------------------------------------------------ #
    def build_order_payload(self, payment: Payment) -> dict[str, Any]:
        """Build the PayPal Orders v2 request body from the trusted record."""
        purchase_unit: dict[str, Any] = {
            "reference_id": payment.reference_id,
            "custom_id": payment.id,  # lets webhooks / reconciliation find our row
            "amount": {
                "currency_code": payment.currency,
                "value": format_amount(from_minor(payment.amount_minor)),
            },
        }
        if payment.description:
            purchase_unit["description"] = payment.description

        return {
            "intent": "CAPTURE",
            "purchase_units": [purchase_unit],
            "application_context": {
                "brand_name": self._settings.APP_NAME,
                "user_action": "PAY_NOW",
                "shipping_preference": "NO_SHIPPING",
                "return_url": self._settings.PAYPAL_RETURN_URL,
                "cancel_url": self._settings.PAYPAL_CANCEL_URL,
            },
        }

    async def create_order(self, request: CreateOrderRequest) -> OrderResponse:
        """Persist a payment record, create the PayPal order, return approval links."""
        self._validate_business_rules(request)

        payment = Payment(
            reference_id=request.reference_id,
            description=request.description,
            currency=request.currency,
            amount_minor=to_minor(request.amount),
            status=PaymentStatus.PENDING.value,
            create_request_id=str(uuid.uuid4()),
        )
        await self._repo.add(payment, event_type="payment.created")
        await self._session.commit()

        logger.info(
            "payment.order.create.requested",
            extra={
                "payment_id": payment.id,
                "request_id": payment.create_request_id,
                "reference_id": payment.reference_id,
                "currency": payment.currency,
                "amount": format_amount(request.amount),
            },
        )

        try:
            data = await self._paypal.create_order(
                self.build_order_payload(payment), payment.create_request_id
            )
        except PayPalAPIError as exc:
            self._repo.transition(
                payment,
                PaymentStatus.FAILED,
                event_type="paypal.order.create.failed",
                detail=f"{exc.error_code}: {exc.detail}",
                paypal_debug_id=exc.debug_id,
            )
            await self._session.commit()
            logger.warning(
                "payment.order.create.failed",
                extra={
                    "payment_id": payment.id,
                    "error_code": exc.error_code,
                    "paypal_debug_id": exc.debug_id,
                },
            )
            raise

        order_id = data.get("id")
        status = data.get("status")
        if not isinstance(order_id, str) or not isinstance(status, str):
            self._repo.transition(
                payment,
                PaymentStatus.FAILED,
                event_type="paypal.order.create.malformed",
                detail="Malformed order response from PayPal",
                paypal_debug_id=data.get("debug_id"),
            )
            await self._session.commit()
            raise PayPalAPIError(
                "Payment provider returned a malformed order response."
            )

        links = [
            OrderLink(
                href=link["href"], rel=link["rel"], method=link.get("method", "GET")
            )
            for link in data.get("links", [])
            if isinstance(link, dict) and "href" in link and "rel" in link
        ]
        if not any(link.rel in _APPROVAL_RELS for link in links):
            self._repo.transition(
                payment,
                PaymentStatus.FAILED,
                event_type="paypal.order.create.no_approval_link",
                detail="PayPal order response had no approval link",
            )
            payment.paypal_order_id = order_id
            await self._session.commit()
            raise PayPalAPIError("Payment provider did not return an approval link.")

        payment.paypal_order_id = order_id
        self._repo.transition(
            payment,
            PaymentStatus.CREATED,
            event_type="paypal.order.created",
            detail=f"paypal_status={status}",
        )
        await self._session.commit()

        logger.info(
            "payment.order.create.succeeded",
            extra={
                "payment_id": payment.id,
                "order_id": order_id,
                "paypal_status": status,
            },
        )
        return OrderResponse(
            order_id=order_id,
            payment_id=payment.id,
            status=PaymentStatus(payment.status),
            request_id=payment.create_request_id,
            links=links,
        )

    # ------------------------------------------------------------------ #
    # Order lookup
    # ------------------------------------------------------------------ #
    async def _load_by_order_id(self, order_id: str) -> Payment:
        payment = await self._repo.get_by_paypal_order_id(order_id)
        if payment is None:
            raise OrderNotFoundError()
        return payment

    def _sync_from_paypal(self, payment: Payment, order: dict[str, Any]) -> None:
        """Apply PayPal's view of the order to our record where it is authoritative."""
        current = PaymentStatus(payment.status)
        paypal_status = order.get("status")

        if paypal_status == "APPROVED" and current is PaymentStatus.CREATED:
            self._repo.transition(
                payment, PaymentStatus.APPROVED, event_type="paypal.order.approved"
            )
        elif paypal_status == "VOIDED" and current in CAPTURABLE_STATES:
            self._repo.transition(
                payment, PaymentStatus.VOIDED, event_type="paypal.order.voided"
            )
        elif paypal_status == "COMPLETED" and current in (
            *CAPTURABLE_STATES,
            PaymentStatus.CAPTURE_PENDING,
        ):
            # Captured outside this flow (or settlement finished). Record the truth.
            self._apply_capture_result(
                payment, order, event_prefix="paypal.order.lookup"
            )

    async def get_order(self, order_id: str) -> OrderStatusResponse:
        """Return the payment record, refreshed from PayPal while it is in flight."""
        payment = await self._load_by_order_id(order_id)
        current = PaymentStatus(payment.status)
        paypal_status: str | None = None

        if not is_terminal(current) and current is not PaymentStatus.CAPTURING:
            try:
                order = await self._paypal.get_order(order_id)
            except PayPalAPIError as exc:
                # Lookup is best-effort for display; the local record stays authoritative.
                logger.warning(
                    "payment.order.lookup.failed",
                    extra={
                        "payment_id": payment.id,
                        "order_id": order_id,
                        "error_code": exc.error_code,
                        "paypal_debug_id": exc.debug_id,
                    },
                )
            except OrderNotFoundError:
                logger.warning(
                    "payment.order.lookup.not_found_at_paypal",
                    extra={"payment_id": payment.id, "order_id": order_id},
                )
            else:
                raw = order.get("status")
                paypal_status = raw if isinstance(raw, str) else None
                self._sync_from_paypal(payment, order)
                await self._session.commit()

        return self._status_response(payment, paypal_status)

    def _status_response(
        self, payment: Payment, paypal_status: str | None
    ) -> OrderStatusResponse:
        return OrderStatusResponse(
            order_id=payment.paypal_order_id or "",
            payment_id=payment.id,
            reference_id=payment.reference_id,
            status=PaymentStatus(payment.status),
            paypal_status=paypal_status,
            amount=_money(payment),
            capture_id=payment.paypal_capture_id,
            created_at=_as_utc(payment.created_at),
            updated_at=_as_utc(payment.updated_at),
        )

    # ------------------------------------------------------------------ #
    # Capture
    # ------------------------------------------------------------------ #
    def _capture_response(self, payment: Payment) -> CaptureResponse:
        return CaptureResponse(
            order_id=payment.paypal_order_id or "",
            payment_id=payment.id,
            capture_id=payment.paypal_capture_id,
            status=PaymentStatus(payment.status),
            amount=_money(payment),
        )

    def _apply_capture_result(
        self, payment: Payment, body: dict[str, Any], *, event_prefix: str
    ) -> None:
        """Record the outcome described by a capture (or completed order) body."""
        capture = _first_capture(body)
        capture_id = capture.get("id") if capture else None
        capture_status = capture.get("status") if capture else None
        debug_id = body.get("debug_id")

        if isinstance(capture_id, str):
            payment.paypal_capture_id = capture_id

        # Flag (but do not hide) a captured amount that differs from our record.
        if capture and isinstance(capture.get("amount"), dict):
            got = (
                capture["amount"].get("currency_code"),
                capture["amount"].get("value"),
            )
            expected = (
                payment.currency,
                format_amount(from_minor(payment.amount_minor)),
            )
            if got != expected:
                logger.error(
                    "payment.capture.captured_amount_mismatch",
                    extra={
                        "payment_id": payment.id,
                        "expected": expected,
                        "captured": got,
                    },
                )
                self._repo.record_event(
                    payment,
                    f"{event_prefix}.captured_amount_mismatch",
                    from_status=payment.status,
                    to_status=payment.status,
                    detail=f"expected={expected[0]} {expected[1]} captured={got[0]} {got[1]}",
                )

        if capture_status == "COMPLETED":
            self._repo.transition(
                payment,
                PaymentStatus.COMPLETED,
                event_type=f"{event_prefix}.completed",
                detail=f"capture_id={capture_id}",
                paypal_debug_id=debug_id,
            )
        elif capture_status == "PENDING":
            if PaymentStatus(payment.status) is not PaymentStatus.CAPTURE_PENDING:
                self._repo.transition(
                    payment,
                    PaymentStatus.CAPTURE_PENDING,
                    event_type=f"{event_prefix}.pending",
                    detail=f"capture_id={capture_id}",
                    paypal_debug_id=debug_id,
                )
        elif capture_status in ("DECLINED", "FAILED"):
            self._repo.transition(
                payment,
                PaymentStatus.FAILED,
                event_type=f"{event_prefix}.declined",
                detail=f"capture_status={capture_status}",
                paypal_debug_id=debug_id,
            )
        elif body.get("status") == "COMPLETED":
            # Order says COMPLETED but no capture detail was returned. Treat as
            # completed; the capture id can be back-filled by lookup or webhook.
            self._repo.transition(
                payment,
                PaymentStatus.COMPLETED,
                event_type=f"{event_prefix}.completed_without_capture_detail",
                paypal_debug_id=debug_id,
            )
        else:
            # Unknown capture status: do not guess. Keep the lock released as APPROVED
            # so a later lookup or retry can resolve it.
            self._repo.transition(
                payment,
                PaymentStatus.APPROVED,
                event_type=f"{event_prefix}.unknown_capture_status",
                detail=f"capture_status={capture_status}",
                paypal_debug_id=debug_id,
            )

    async def _release_capture_lock(
        self,
        payment: Payment,
        target: PaymentStatus,
        *,
        event_type: str,
        detail: str | None = None,
        paypal_debug_id: str | None = None,
    ) -> None:
        self._repo.transition(
            payment,
            target,
            event_type=event_type,
            detail=detail,
            paypal_debug_id=paypal_debug_id,
        )
        await self._session.commit()

    async def _resolve_uncertain_capture(
        self, payment: Payment, order_id: str, cause: PayPalAPIError
    ) -> CaptureResponse:
        """The capture call failed without a definitive answer. Ask PayPal what happened."""
        logger.warning(
            "payment.capture.outcome_uncertain",
            extra={
                "payment_id": payment.id,
                "order_id": order_id,
                "error_code": cause.error_code,
                "paypal_debug_id": cause.debug_id,
            },
        )
        try:
            order = await self._paypal.get_order(order_id)
        except (PayPalAPIError, OrderNotFoundError):
            await self._release_capture_lock(
                payment,
                PaymentStatus.APPROVED,
                event_type="paypal.capture.outcome_unknown",
                detail=f"{cause.error_code}; verification lookup also failed",
                paypal_debug_id=cause.debug_id,
            )
            raise cause from None

        if order.get("status") == "COMPLETED":
            self._apply_capture_result(
                payment, order, event_prefix="paypal.capture.recovered"
            )
            await self._session.commit()
            return self._capture_response(payment)

        await self._release_capture_lock(
            payment,
            PaymentStatus.APPROVED,
            event_type="paypal.capture.not_performed",
            detail=f"{cause.error_code}; order status {order.get('status')}",
            paypal_debug_id=cause.debug_id,
        )
        raise cause

    async def capture_order(self, order_id: str) -> CaptureResponse:
        """Capture an approved order exactly once."""
        payment = await self._load_by_order_id(order_id)
        current = PaymentStatus(payment.status)

        # Idempotent replays.
        if (
            current is PaymentStatus.COMPLETED
            or current is PaymentStatus.CAPTURE_PENDING
        ):
            logger.info(
                "payment.capture.replayed",
                extra={
                    "payment_id": payment.id,
                    "order_id": order_id,
                    "status": current,
                },
            )
            return self._capture_response(payment)
        if current is PaymentStatus.CAPTURING:
            raise CaptureInProgressError()
        if current not in CAPTURABLE_STATES:
            raise PaymentStateError(
                f"Payment is {current.value} and cannot be captured."
            )

        # Atomic lock: only one caller (across processes) gets past this point.
        won = await self._repo.try_begin_capture(payment.id)
        if not won:
            await self._session.rollback()
            await self._repo.refresh(payment)
            if PaymentStatus(payment.status) is PaymentStatus.COMPLETED:
                return self._capture_response(payment)
            raise CaptureInProgressError()

        previous = current
        payment.status = (
            PaymentStatus.CAPTURING.value
        )  # mirror the SQL UPDATE in memory
        if payment.capture_request_id is None:
            payment.capture_request_id = str(uuid.uuid4())
        self._repo.record_event(
            payment,
            "payment.capture.started",
            from_status=previous.value,
            to_status=PaymentStatus.CAPTURING.value,
            detail=f"capture_request_id={payment.capture_request_id}",
        )
        await self._session.commit()

        logger.info(
            "payment.capture.requested",
            extra={
                "payment_id": payment.id,
                "order_id": order_id,
                "capture_request_id": payment.capture_request_id,
            },
        )

        # Re-read the order from PayPal and verify it is ours and approved.
        try:
            order = await self._paypal.get_order(order_id)
        except (PayPalAPIError, OrderNotFoundError) as exc:
            await self._release_capture_lock(
                payment,
                previous,
                event_type="paypal.capture.verify_failed",
                detail=exc.error_code,
                paypal_debug_id=exc.debug_id,
            )
            raise

        try:
            self._verify_order_matches_record(payment, order)
        except AmountMismatchError:
            await self._release_capture_lock(
                payment,
                PaymentStatus.FAILED,
                event_type="paypal.capture.amount_mismatch",
                detail="PayPal order amount/currency differ from backend record",
            )
            raise

        paypal_status = order.get("status")
        if paypal_status == "COMPLETED":
            self._apply_capture_result(
                payment, order, event_prefix="paypal.capture.already"
            )
            await self._session.commit()
            return self._capture_response(payment)
        if paypal_status == "VOIDED":
            await self._release_capture_lock(
                payment, PaymentStatus.VOIDED, event_type="paypal.order.voided"
            )
            raise PaymentStateError(
                "The order was voided at PayPal and cannot be captured."
            )
        if paypal_status != "APPROVED":
            await self._release_capture_lock(
                payment,
                PaymentStatus.CREATED,
                event_type="paypal.capture.not_approved",
                detail=f"paypal_status={paypal_status}",
            )
            raise OrderNotApprovedError()

        # Capture with the stable request id.
        try:
            result = await self._paypal.capture_order(
                order_id, payment.capture_request_id
            )
        except OrderNotFoundError as exc:
            await self._release_capture_lock(
                payment,
                PaymentStatus.APPROVED,
                event_type="paypal.capture.order_missing",
                paypal_debug_id=exc.debug_id,
            )
            raise
        except PayPalAPIError as exc:
            if not exc.is_client_error:
                return await self._resolve_uncertain_capture(payment, order_id, exc)
            if exc.issue in _ALREADY_CAPTURED_ISSUES:
                return await self._resolve_uncertain_capture(payment, order_id, exc)
            if exc.issue in _DECLINED_ISSUES:
                await self._release_capture_lock(
                    payment,
                    PaymentStatus.APPROVED,
                    event_type="paypal.capture.instrument_declined",
                    detail=exc.issue,
                    paypal_debug_id=exc.debug_id,
                )
                raise PaymentDeclinedError(debug_id=exc.debug_id) from exc
            if exc.issue in _NOT_APPROVED_ISSUES:
                await self._release_capture_lock(
                    payment,
                    PaymentStatus.CREATED,
                    event_type="paypal.capture.not_approved",
                    detail=exc.issue,
                    paypal_debug_id=exc.debug_id,
                )
                raise OrderNotApprovedError(debug_id=exc.debug_id) from exc
            await self._release_capture_lock(
                payment,
                PaymentStatus.FAILED,
                event_type="paypal.capture.rejected",
                detail=f"{exc.paypal_name or 'PAYPAL_ERROR'}: {exc.issue or exc.detail}",
                paypal_debug_id=exc.debug_id,
            )
            raise

        self._apply_capture_result(payment, result, event_prefix="paypal.capture")
        await self._session.commit()

        logger.info(
            "payment.capture.finished",
            extra={
                "payment_id": payment.id,
                "order_id": order_id,
                "status": payment.status,
                "capture_id": payment.paypal_capture_id,
            },
        )
        return self._capture_response(payment)
