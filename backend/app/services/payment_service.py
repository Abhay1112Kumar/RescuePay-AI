"""Payment domain business logic.

The backend's ``Payment`` row records a payable validated against an injected
backend authority. With no authority configured, creation/capture fail closed.

1. ``create_order``: validate the authoritative payable, persist the caller's
   unique operation key, then create a provider order once. Ambiguous failures
   stay CREATION_UNCERTAIN; a replay cannot create a separate provider order.
2. ``get_order``: return the local record, refreshed from PayPal when the
   payment is still in flight (APPROVED / VOIDED / out-of-band COMPLETED).
3. ``capture_order``: take an atomic CAPTURING lock, re-read the order from
   PayPal, verify order/merchant identity and money, capture with a stable
   request id, and only mark COMPLETED from matching full-capture details.
   Timeouts/unknown outcomes stay CAPTURE_UNCERTAIN and reconcile via GET.
   Version checks prevent stale writes; expired locks never authorize a new POST.

Every state change is written together with an audit event in one transaction.
"""

import logging
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.config import Settings
from app.core.exceptions import (
    AmountMismatchError,
    CaptureInProgressError,
    CaptureUncertainError,
    CreationUncertainError,
    IdempotencyConflictError,
    OrderNotApprovedError,
    OrderNotFoundError,
    PayablesNotConfiguredError,
    PaymentDeclinedError,
    PaymentStateError,
    PaymentValidationError,
    PaymentVerificationError,
    PayPalAPIError,
    PayPalNotConfiguredError,
    RescuePayError,
)
from app.integrations.paypal import PayPalClient
from app.models.payment import Payment
from app.repositories.payment_repository import PaymentRepository
from app.schemas.payment import (
    ORDER_ID_PATTERN,
    CaptureResponse,
    CreateOrderRequest,
    MoneyAmount,
    OrderLink,
    OrderResponse,
    OrderStatusResponse,
)
from app.services.payables import PayableSource
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
        *,
        payable_source: PayableSource | None = None,
    ) -> None:
        self._session = session
        self._repo = PaymentRepository(session)
        self._paypal = paypal_client
        self._settings = settings
        self._payables = payable_source

    async def _commit(self, payment: Payment) -> bool:
        """Never let an old lookup/capture overwrite a newer transaction."""
        try:
            await self._session.commit()
        except StaleDataError:
            await self._session.rollback()
            await self._repo.refresh(payment)
            return False
        except IntegrityError:
            # A provider identifier already belongs to another record. Roll back
            # both the attempted success and its event, then quarantine safely.
            await self._session.rollback()
            await self._repo.refresh(payment)
            current = PaymentStatus(payment.status)
            if not is_terminal(current):
                if current in (PaymentStatus.PENDING, PaymentStatus.CREATION_UNCERTAIN):
                    target = PaymentStatus.CREATION_UNCERTAIN
                else:
                    target = PaymentStatus.CAPTURE_UNCERTAIN
                if current is not target:
                    self._repo.transition(
                        payment, target, event_type="payment.provider_identity_conflict"
                    )
                else:
                    self._repo.record_event(
                        payment,
                        "payment.provider_identity_conflict",
                        from_status=current.value,
                        to_status=current.value,
                    )
                try:
                    await self._session.commit()
                except StaleDataError:
                    await self._session.rollback()
                    await self._repo.refresh(payment)
            return False
        return True

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
        if self._payables is None:
            raise PayablesNotConfiguredError()
        payable = self._payables.resolve(request.reference_id)
        if (payable.reference_id, payable.currency, payable.amount) != (
            request.reference_id,
            request.currency,
            request.amount,
        ):
            raise PaymentValidationError(
                "Request does not match the backend-authorized payable."
            )
        if not self._settings.PAYPAL_MERCHANT_ID:
            raise PayPalNotConfiguredError(
                "The Sandbox merchant identity is not configured."
            )

    def _verify_identity(
        self, payment: Payment, order: dict[str, Any]
    ) -> dict[str, Any]:
        units = order.get("purchase_units")
        if (
            order.get("id") != payment.paypal_order_id
            or order.get("intent") != "CAPTURE"
            or not isinstance(units, list)
            or len(units) != 1
            or not isinstance(units[0], dict)
        ):
            raise PaymentVerificationError()
        unit = units[0]
        payee = unit.get("payee")
        if (
            unit.get("reference_id") != payment.reference_id
            or unit.get("custom_id") != payment.id
            or not self._settings.PAYPAL_MERCHANT_ID
            or not isinstance(payee, dict)
            or payee.get("merchant_id") != self._settings.PAYPAL_MERCHANT_ID
        ):
            raise PaymentVerificationError()
        return unit

    @staticmethod
    def _verify_money(payment: Payment, amount: Any) -> None:
        if (
            not isinstance(amount, dict)
            or amount.get("currency_code") != payment.currency
        ):
            raise AmountMismatchError()
        value = amount.get("value")
        if not isinstance(value, str):
            raise AmountMismatchError()
        try:
            money = Decimal(value)
        except ArithmeticError:
            raise AmountMismatchError() from None
        if not money.is_finite() or money != from_minor(payment.amount_minor):
            raise AmountMismatchError()

    def _verify_order_matches_record(
        self, payment: Payment, order: dict[str, Any]
    ) -> None:
        """Refuse to proceed if PayPal's order amount/currency differ from our record."""
        unit = self._verify_identity(payment, order)
        self._verify_money(payment, unit.get("amount"))

    # ------------------------------------------------------------------ #
    # Order creation
    # ------------------------------------------------------------------ #
    async def create_checkout(
        self, item_id: str, *, idempotency_key: str
    ) -> OrderResponse:
        if self._payables is None:
            raise PayablesNotConfiguredError()
        payable = self._payables.resolve(item_id)
        return await self.create_order(
            CreateOrderRequest(
                reference_id=payable.reference_id,
                currency=payable.currency,
                amount=payable.amount,
                description=payable.description,
            ),
            idempotency_key=idempotency_key,
        )

    def build_order_payload(self, payment: Payment) -> dict[str, Any]:
        """Build the PayPal Orders v2 request body from the trusted record."""
        purchase_unit: dict[str, Any] = {
            "reference_id": payment.reference_id,
            "custom_id": payment.id,  # lets webhooks / reconciliation find our row
            "payee": {"merchant_id": self._settings.PAYPAL_MERCHANT_ID},
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

    async def create_order(
        self, request: CreateOrderRequest, *, idempotency_key: str | None = None
    ) -> OrderResponse:
        """Persist a payment record, create the PayPal order, return approval links."""
        key = str(uuid.UUID(idempotency_key)) if idempotency_key else str(uuid.uuid4())
        existing = await self._repo.get_by_creation_key(key)
        if existing is not None:
            return self._replay_creation(existing, request)
        self._validate_business_rules(request)

        payment = Payment(
            reference_id=request.reference_id,
            description=request.description,
            currency=request.currency,
            amount_minor=to_minor(request.amount),
            status=PaymentStatus.PENDING.value,
            create_request_id=str(uuid.uuid4()),
            creation_key=key,
        )
        try:
            await self._repo.add(payment, event_type="payment.created")
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            existing = await self._repo.get_by_creation_key(key)
            if existing is None:
                raise
            return self._replay_creation(existing, request)

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
        except RescuePayError as exc:
            self._repo.transition(
                payment,
                PaymentStatus.FAILED
                if isinstance(exc, PayPalAPIError) and exc.is_client_error
                else PaymentStatus.CREATION_UNCERTAIN,
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
        if (
            not isinstance(order_id, str)
            or not re.fullmatch(ORDER_ID_PATTERN, order_id)
            or not isinstance(status, str)
        ):
            self._repo.transition(
                payment,
                PaymentStatus.CREATION_UNCERTAIN,
                event_type="paypal.order.create.malformed",
                detail="Malformed order response from PayPal",
                paypal_debug_id=data.get("debug_id"),
            )
            await self._session.commit()
            raise PayPalAPIError(
                "Payment provider returned a malformed order response."
            )

        raw_links = data.get("links")
        links = [
            OrderLink(
                href=link["href"], rel=link["rel"], method=link.get("method", "GET")
            )
            for link in (raw_links if isinstance(raw_links, list) else [])
            if isinstance(link, dict)
            and isinstance(link.get("href"), str)
            and isinstance(link.get("rel"), str)
            and isinstance(link.get("method", "GET"), str)
        ]
        approval = next(
            (
                link
                for link in links
                if link.rel in _APPROVAL_RELS and self._safe_approval(link, order_id)
            ),
            None,
        )
        if approval is None:
            self._repo.transition(
                payment,
                PaymentStatus.CREATION_UNCERTAIN,
                event_type="paypal.order.create.no_approval_link",
                detail="PayPal order response had no approval link",
            )
            payment.paypal_order_id = order_id
            await self._session.commit()
            raise PayPalAPIError("Payment provider did not return an approval link.")

        payment.paypal_order_id = order_id
        payment.approval_url = approval.href
        self._repo.transition(
            payment,
            PaymentStatus.CREATED,
            event_type="paypal.order.created",
            detail=f"paypal_status={status}",
        )
        if not await self._commit(payment):
            raise CreationUncertainError()

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
            links=[link for link in links if link.rel not in _APPROVAL_RELS]
            + [approval],
        )

    @staticmethod
    def _safe_approval(link: OrderLink, order_id: str) -> bool:
        try:
            url = urlsplit(link.href)
            return (
                link.method == "GET"
                and url.scheme == "https"
                and url.hostname == "www.sandbox.paypal.com"
                and url.port in (None, 443)
                and not url.username
                and not url.password
                and url.path == "/checkoutnow"
                and not url.fragment
                and parse_qs(url.query).get("token") == [order_id]
            )
        except ValueError:
            return False

    def _replay_creation(
        self, payment: Payment, request: CreateOrderRequest
    ) -> OrderResponse:
        if (
            payment.reference_id,
            payment.currency,
            payment.amount_minor,
            payment.description,
        ) != (
            request.reference_id,
            request.currency,
            to_minor(request.amount),
            request.description,
        ):
            raise IdempotencyConflictError()
        if not payment.paypal_order_id or not payment.approval_url:
            raise CreationUncertainError()
        if not self._safe_approval(
            OrderLink(href=payment.approval_url, rel="approve"), payment.paypal_order_id
        ):
            raise CreationUncertainError()
        return OrderResponse(
            order_id=payment.paypal_order_id,
            payment_id=payment.id,
            status=PaymentStatus(payment.status),
            request_id=payment.create_request_id,
            links=[OrderLink(href=payment.approval_url, rel="approve")],
        )

    # ------------------------------------------------------------------ #
    # Order lookup
    # ------------------------------------------------------------------ #
    async def _load_by_order_id(self, order_id: str) -> Payment:
        payment = await self._repo.get_by_paypal_order_id(order_id)
        if payment is None:
            raise OrderNotFoundError()
        return payment

    def _sync_from_paypal(self, payment: Payment, order: dict[str, Any]) -> bool:
        """Apply PayPal's view of the order to our record where it is authoritative."""
        current = PaymentStatus(payment.status)
        paypal_status = order.get("status")

        try:
            self._verify_order_matches_record(payment, order)
        except (AmountMismatchError, PaymentVerificationError):
            self._mark_uncertain(payment, event_type="paypal.order.lookup.unverified")
            return False

        if paypal_status == "COMPLETED" or _first_capture(order) is not None:
            return self._apply_capture_result(
                payment, order, event_prefix="paypal.order.lookup"
            )

        if paypal_status == "APPROVED" and current is PaymentStatus.CREATED:
            self._repo.transition(
                payment, PaymentStatus.APPROVED, event_type="paypal.order.approved"
            )
        elif paypal_status == "VOIDED" and current in CAPTURABLE_STATES:
            self._repo.transition(
                payment, PaymentStatus.VOIDED, event_type="paypal.order.voided"
            )
        # APPROVED after a timed-out capture does not prove that no capture is
        # still in flight. An uncertain payment is never made capturable here.
        return True

    def _capture_lease_expired(self, payment: Payment) -> bool:
        return (
            datetime.now(UTC) - _as_utc(payment.updated_at)
        ).total_seconds() >= self._settings.PAYMENT_CAPTURE_LEASE_SECONDS

    async def get_order(self, order_id: str) -> OrderStatusResponse:
        """Return the payment record, refreshed from PayPal while it is in flight."""
        payment = await self._load_by_order_id(order_id)
        current = PaymentStatus(payment.status)
        paypal_status: str | None = None
        provider_refreshed = False

        if current is PaymentStatus.CAPTURING and self._capture_lease_expired(payment):
            self._mark_uncertain(payment, event_type="payment.capture.lease_expired")
            await self._commit(payment)
            current = PaymentStatus(payment.status)

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
                provider_refreshed = self._sync_from_paypal(payment, order)
                if not await self._commit(payment):
                    provider_refreshed = False
                    paypal_status = None

        return self._status_response(payment, paypal_status, provider_refreshed)

    def _status_response(
        self,
        payment: Payment,
        paypal_status: str | None,
        provider_refreshed: bool = False,
    ) -> OrderStatusResponse:
        return OrderStatusResponse(
            order_id=payment.paypal_order_id or "",
            payment_id=payment.id,
            reference_id=payment.reference_id,
            status=PaymentStatus(payment.status),
            paypal_status=paypal_status,
            provider_refreshed=provider_refreshed,
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

    def _mark_uncertain(self, payment: Payment, *, event_type: str) -> None:
        if PaymentStatus(payment.status) is PaymentStatus.CAPTURE_UNCERTAIN:
            self._repo.record_event(
                payment,
                event_type,
                from_status=payment.status,
                to_status=payment.status,
            )
        else:
            self._repo.transition(
                payment, PaymentStatus.CAPTURE_UNCERTAIN, event_type=event_type
            )

    def _apply_capture_result(
        self, payment: Payment, body: dict[str, Any], *, event_prefix: str
    ) -> bool:
        """Only verified single full-capture evidence may establish payment success."""
        try:
            # Legacy rows may originate from caller-selected prices. A migration
            # quarantines old success, and lookup must not bypass price authority
            # when re-establishing success under the stricter rules.
            self._validate_business_rules(
                CreateOrderRequest(
                    reference_id=payment.reference_id,
                    currency=payment.currency,
                    amount=from_minor(payment.amount_minor),
                    description=payment.description,
                )
            )
            unit = self._verify_identity(payment, body)
            if "amount" in unit:
                self._verify_money(payment, unit["amount"])
            payments = unit.get("payments")
            captures = payments.get("captures") if isinstance(payments, dict) else None
            if (
                not isinstance(captures, list)
                or len(captures) != 1
                or not isinstance(captures[0], dict)
            ):
                raise PaymentVerificationError()
            capture = captures[0]
            capture_id = capture.get("id")
            if not isinstance(capture_id, str) or not capture_id.strip():
                raise PaymentVerificationError()
            if payment.paypal_capture_id and payment.paypal_capture_id != capture_id:
                raise PaymentVerificationError()
            self._verify_money(payment, capture.get("amount"))
            status = capture.get("status")
            if (
                body.get("status") != "COMPLETED"
                or capture.get("final_capture") is not True
            ):
                raise PaymentVerificationError()
            target = {
                "COMPLETED": PaymentStatus.COMPLETED,
                "PENDING": PaymentStatus.CAPTURE_PENDING,
                "DECLINED": PaymentStatus.FAILED,
                "FAILED": PaymentStatus.FAILED,
            }.get(status)
            if target is None:
                raise PaymentVerificationError()
        except (
            AmountMismatchError,
            PaymentVerificationError,
            PaymentValidationError,
            PayablesNotConfiguredError,
            PayPalNotConfiguredError,
        ):
            self._mark_uncertain(payment, event_type=f"{event_prefix}.unverified")
            return False

        payment.paypal_capture_id = capture_id
        if PaymentStatus(payment.status) is not target:
            suffix = {
                PaymentStatus.COMPLETED: "completed",
                PaymentStatus.CAPTURE_PENDING: "pending",
                PaymentStatus.FAILED: "declined",
            }[target]
            self._repo.transition(
                payment,
                target,
                event_type=f"{event_prefix}.{suffix}",
                detail=f"capture_id={capture_id}",
            )
        return True

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
        await self._commit(payment)

    async def _resolve_uncertain_capture(
        self, payment: Payment, order_id: str, cause: RescuePayError
    ) -> CaptureResponse:
        """Persist uncertainty first. Reconcile by GET, never by another capture POST."""
        self._mark_uncertain(payment, event_type="paypal.capture.outcome_uncertain")
        await self._commit(payment)
        if is_terminal(PaymentStatus(payment.status)):
            if PaymentStatus(payment.status) is PaymentStatus.COMPLETED:
                return self._capture_response(payment)
            raise CaptureUncertainError(debug_id=cause.debug_id)
        try:
            order = await self._paypal.get_order(order_id)
        except RescuePayError:
            raise CaptureUncertainError(debug_id=cause.debug_id) from None
        self._sync_from_paypal(payment, order)
        await self._commit(payment)
        if PaymentStatus(payment.status) in (
            PaymentStatus.COMPLETED,
            PaymentStatus.CAPTURE_PENDING,
        ):
            return self._capture_response(payment)
        raise CaptureUncertainError(debug_id=cause.debug_id)

    async def capture_order(self, order_id: str) -> CaptureResponse:
        """Serialize a capture and reconcile uncertain attempts without recharging."""
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
        if current is PaymentStatus.CAPTURE_UNCERTAIN or (
            current is PaymentStatus.CAPTURING and self._capture_lease_expired(payment)
        ):
            await self.get_order(order_id)
            await self._repo.refresh(payment)
            if PaymentStatus(payment.status) in (
                PaymentStatus.COMPLETED,
                PaymentStatus.CAPTURE_PENDING,
            ):
                return self._capture_response(payment)
            raise CaptureUncertainError()
        if current is PaymentStatus.CAPTURING:
            raise CaptureInProgressError()
        if current not in CAPTURABLE_STATES:
            raise PaymentStateError(
                f"Payment is {current.value} and cannot be captured."
            )

        # Atomic lock: only one caller (across processes) gets past this point.
        if self._payables is None:
            raise PayablesNotConfiguredError()
        self._validate_business_rules(
            CreateOrderRequest(
                reference_id=payment.reference_id,
                currency=payment.currency,
                amount=from_minor(payment.amount_minor),
                description=payment.description,
            )
        )
        won = await self._repo.try_begin_capture(payment.id, payment.version)
        if not won:
            await self._session.rollback()
            await self._repo.refresh(payment)
            if PaymentStatus(payment.status) is PaymentStatus.COMPLETED:
                return self._capture_response(payment)
            raise CaptureInProgressError()

        previous = current
        await self._repo.refresh(payment)
        if payment.capture_request_id is None:
            payment.capture_request_id = str(uuid.uuid4())
        self._repo.record_event(
            payment,
            "payment.capture.started",
            from_status=previous.value,
            to_status=PaymentStatus.CAPTURING.value,
            detail=f"capture_request_id={payment.capture_request_id}",
        )
        if not await self._commit(payment):
            raise CaptureInProgressError()
        capture_version = payment.version

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
        except RescuePayError as exc:
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
        except (AmountMismatchError, PaymentVerificationError):
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
            await self._commit(payment)
            return self._capture_response(payment)
        if order["purchase_units"][0].get("payments") is not None:
            # Any capture evidence must be reconciled, never followed by a new POST.
            return await self._resolve_uncertain_capture(
                payment, order_id, PaymentVerificationError()
            )
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
        await self._repo.refresh(payment)
        if (
            payment.status != PaymentStatus.CAPTURING
            or payment.version != capture_version
            or self._capture_lease_expired(payment)
        ):
            if payment.status in (
                PaymentStatus.COMPLETED,
                PaymentStatus.CAPTURE_PENDING,
            ):
                return self._capture_response(payment)
            raise CaptureUncertainError()
        try:
            result = await self._paypal.capture_order(
                order_id, payment.capture_request_id
            )
        except RescuePayError as exc:
            if isinstance(exc, PayPalAPIError) and exc.issue in _DECLINED_ISSUES:
                await self._release_capture_lock(
                    payment,
                    PaymentStatus.APPROVED,
                    event_type="paypal.capture.instrument_declined",
                    detail=exc.issue,
                    paypal_debug_id=exc.debug_id,
                )
                raise PaymentDeclinedError(debug_id=exc.debug_id) from exc
            if isinstance(exc, PayPalAPIError) and exc.issue in _NOT_APPROVED_ISSUES:
                await self._release_capture_lock(
                    payment,
                    PaymentStatus.CREATED,
                    event_type="paypal.capture.not_approved",
                    detail=exc.issue,
                    paypal_debug_id=exc.debug_id,
                )
                raise OrderNotApprovedError(debug_id=exc.debug_id) from exc
            return await self._resolve_uncertain_capture(payment, order_id, exc)

        self._apply_capture_result(payment, result, event_prefix="paypal.capture")
        await self._commit(payment)

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
