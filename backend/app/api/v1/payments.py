"""Payment endpoints: order creation, retrieval, and capture."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, status

from app.api.v1.checkout import require_checkout
from app.api.v1.deps import get_payment_service
from app.schemas.payment import (
    ORDER_ID_PATTERN,
    CaptureResponse,
    CheckoutRequest,
    ErrorResponse,
    OrderResponse,
    OrderStatusResponse,
)
from app.services.payment_service import PaymentService

router = APIRouter()

_COMMON_ERRORS = {
    502: {"model": ErrorResponse, "description": "Payment provider error"},
    503: {
        "model": ErrorResponse,
        "description": "Provider or authoritative payables not configured",
    },
    504: {"model": ErrorResponse, "description": "Payment provider timeout"},
}

_ORDER_ID = Path(pattern=ORDER_ID_PATTERN, examples=["5O190127TN364715T"])


@router.post(
    "/orders",
    response_model=OrderResponse,
    dependencies=[Depends(require_checkout)],
    status_code=status.HTTP_201_CREATED,
    summary="Create PayPal order",
    description=(
        "Records the payment, creates a PayPal checkout order and returns the "
        "approval link the buyer must visit. Nothing is charged until capture."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Business validation failed"},
        409: {
            "model": ErrorResponse,
            "description": "Operation key conflict or unresolved creation",
        },
        422: {"model": ErrorResponse, "description": "Schema validation failed"},
        **_COMMON_ERRORS,
    },
)
async def create_order(
    payload: CheckoutRequest,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    service: PaymentService = Depends(get_payment_service),
) -> OrderResponse:
    """Create a new order at PayPal."""
    return await service.create_checkout(
        payload.item_id, idempotency_key=str(idempotency_key)
    )


@router.get(
    "/orders/{order_id}",
    response_model=OrderStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get payment status",
    description=(
        "Returns the backend payment record for a PayPal order, refreshed from "
        "PayPal while the payment is still in progress."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Order not found"},
        422: {"model": ErrorResponse, "description": "Malformed order id"},
        **_COMMON_ERRORS,
    },
)
async def get_order(
    order_id: str = _ORDER_ID,
    service: PaymentService = Depends(get_payment_service),
) -> OrderStatusResponse:
    """Fetch the payment state."""
    return await service.get_order(order_id)


@router.post(
    "/orders/{order_id}/capture",
    response_model=CaptureResponse,
    dependencies=[Depends(require_checkout)],
    status_code=status.HTTP_200_OK,
    summary="Capture an approved order",
    description=(
        "Captures funds for an order the buyer has approved. The backend verifies "
        "the order's amount and currency against its own record before capturing. "
        "A repeated call on a verified captured payment returns the same result. "
        "An uncertain attempt is reconciled by status lookup and is not captured again."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Order not found"},
        409: {
            "model": ErrorResponse,
            "description": (
                "Not capturable: ORDER_NOT_APPROVED, CAPTURE_IN_PROGRESS, "
                "PAYMENT_INSTRUMENT_DECLINED, AMOUNT_MISMATCH, PAYMENT_INVALID_STATE, "
                "PAYMENT_VERIFICATION_FAILED, CAPTURE_OUTCOME_UNCERTAIN"
            ),
        },
        422: {"model": ErrorResponse, "description": "Malformed order id"},
        **_COMMON_ERRORS,
    },
)
async def capture_order(
    order_id: str = _ORDER_ID,
    service: PaymentService = Depends(get_payment_service),
) -> CaptureResponse:
    """Serialize capture; reconcile unknown outcomes without a blind retry."""
    return await service.capture_order(order_id)
