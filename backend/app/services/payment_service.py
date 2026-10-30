"""Payment domain business logic.

Phase 2 scope: create a PayPal order and read its status. The service owns all
business validation (currency allowlist, amount ceiling) so those rules are
enforced regardless of which API surface calls it.

Trust note: at this phase there is no persisted internal record of what is being
paid for, so the requested amount is accepted from the caller but constrained by
backend limits. Phase 3 (persistence) replaces this with amounts derived from a
backend-owned record, and capture will compare PayPal's order amount against it.
"""

import logging
import uuid
from decimal import Decimal
from typing import Any

from app.core.config import Settings
from app.core.exceptions import PaymentValidationError, PayPalAPIError
from app.integrations.paypal import PayPalClient
from app.schemas.payment import (
    CreateOrderRequest,
    MoneyAmount,
    OrderLink,
    OrderResponse,
    OrderStatusResponse,
)

logger = logging.getLogger(__name__)

# PayPal returns the buyer redirect as rel="approve" (application_context flow) or
# rel="payer-action" (payment_source flow). Accept either.
_APPROVAL_RELS = ("approve", "payer-action")


def format_amount(amount: Decimal) -> str:
    """Render a Decimal as PayPal expects: two decimal places, no exponent."""
    return f"{amount.quantize(Decimal('0.01')):f}"


class PaymentService:
    """Service handling payment operations, lifecycle, and transaction workflows."""

    def __init__(self, paypal_client: PayPalClient, settings: Settings) -> None:
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

    # ------------------------------------------------------------------ #
    # Operations
    # ------------------------------------------------------------------ #
    def build_order_payload(self, request: CreateOrderRequest) -> dict[str, Any]:
        """Build the PayPal Orders v2 request body."""
        purchase_unit: dict[str, Any] = {
            "reference_id": request.reference_id,
            "amount": {
                "currency_code": request.currency,
                "value": format_amount(request.amount),
            },
        }
        if request.description:
            purchase_unit["description"] = request.description

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
        """Validate the request, create the order at PayPal, and return approval links."""
        self._validate_business_rules(request)

        request_id = str(uuid.uuid4())
        logger.info(
            "payment.order.create.requested",
            extra={
                "request_id": request_id,
                "reference_id": request.reference_id,
                "currency": request.currency,
                "amount": format_amount(request.amount),
            },
        )

        payload = self.build_order_payload(request)
        try:
            data = await self._paypal.create_order(payload, request_id)
        except PayPalAPIError as exc:
            logger.warning(
                "payment.order.create.failed",
                extra={
                    "request_id": request_id,
                    "error_code": exc.error_code,
                    "paypal_debug_id": exc.debug_id,
                },
            )
            raise

        order_id = data.get("id")
        status = data.get("status")
        if not isinstance(order_id, str) or not isinstance(status, str):
            logger.error(
                "payment.order.create.malformed_response",
                extra={
                    "request_id": request_id,
                    "paypal_debug_id": data.get("debug_id"),
                },
            )
            raise PayPalAPIError(
                "Payment provider returned a malformed order response."
            )

        links = [
            OrderLink(
                href=link["href"],
                rel=link["rel"],
                method=link.get("method", "GET"),
            )
            for link in data.get("links", [])
            if isinstance(link, dict) and "href" in link and "rel" in link
        ]
        if not any(link.rel in _APPROVAL_RELS for link in links):
            logger.error(
                "payment.order.create.missing_approval_link",
                extra={"request_id": request_id, "order_id": order_id},
            )
            raise PayPalAPIError("Payment provider did not return an approval link.")

        logger.info(
            "payment.order.create.succeeded",
            extra={"request_id": request_id, "order_id": order_id, "status": status},
        )
        return OrderResponse(
            order_id=order_id,
            status=status,
            request_id=request_id,
            links=links,
        )

    async def get_order(self, order_id: str) -> OrderStatusResponse:
        """Fetch the current order state from PayPal."""
        data = await self._paypal.get_order(order_id)

        amount: MoneyAmount | None = None
        units = data.get("purchase_units")
        if isinstance(units, list) and units:
            raw_amount = units[0].get("amount") if isinstance(units[0], dict) else None
            if (
                isinstance(raw_amount, dict)
                and {"currency_code", "value"} <= raw_amount.keys()
            ):
                amount = MoneyAmount(
                    currency_code=str(raw_amount["currency_code"]),
                    value=str(raw_amount["value"]),
                )

        return OrderStatusResponse(
            order_id=str(data.get("id", order_id)),
            status=str(data.get("status", "UNKNOWN")),
            created_at=data.get("create_time"),
            amount=amount,
        )
