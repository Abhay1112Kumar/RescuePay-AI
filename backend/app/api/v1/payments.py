"""Payment endpoints: order creation, retrieval, and capture."""

from fastapi import APIRouter, Depends, Path, status

from app.api.v1.deps import get_payment_service
from app.schemas.payment import (
    ORDER_ID_PATTERN,
    CaptureResponse,
    CreateOrderRequest,
    ErrorResponse,
    OrderResponse,
    OrderStatusResponse,
)
from app.services.payment_service import PaymentService

router = APIRouter()

_COMMON_ERRORS = {
    502: {"model": ErrorResponse, "description": "Payment provider error"},
    503: {"model": ErrorResponse, "description": "Payment provider not configured"},
    504: {"model": ErrorResponse, "description": "Payment provider timeout"},
}

_ORDER_ID = Path(pattern=ORDER_ID_PATTERN, examples=["5O190127TN364715T"])


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create PayPal order",
    description=(
        "Records the payment, creates a PayPal checkout order and returns the "
        "approval link the buyer must visit. Nothing is charged until capture."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Business validation failed"},
        422: {"model": ErrorResponse, "description": "Schema validation failed"},
        **_COMMON_ERRORS,
    },
)
async def create_order(
    payload: CreateOrderRequest,
    service: PaymentService = Depends(get_payment_service),
) -> OrderResponse:
    """Create a new order at PayPal."""
    return await service.create_order(payload)


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
    status_code=status.HTTP_200_OK,
    summary="Capture an approved order",
    description=(
        "Captures funds for an order the buyer has approved. The backend verifies "
        "the order's amount and currency against its own record before capturing. "
        "Safe to retry: a repeated call on a captured payment returns the same result."
    ),
    responses={
        404: {"model": ErrorResponse, "description": "Order not found"},
        409: {
            "model": ErrorResponse,
            "description": (
                "Not capturable: ORDER_NOT_APPROVED, CAPTURE_IN_PROGRESS, "
                "PAYMENT_INSTRUMENT_DECLINED, AMOUNT_MISMATCH, PAYMENT_INVALID_STATE"
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
    """Capture the order exactly once."""
    return await service.capture_order(order_id)
