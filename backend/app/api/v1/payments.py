"""Payment endpoints: order creation and retrieval."""

from fastapi import APIRouter, Depends, Path, status

from app.api.v1.deps import get_payment_service
from app.schemas.payment import (
    ORDER_ID_PATTERN,
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


@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create PayPal order",
    description=(
        "Creates a PayPal checkout order and returns the approval link the buyer "
        "must visit. The amount is validated against backend limits; it is not "
        "captured until the capture endpoint is called."
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
    summary="Get PayPal order status",
    description="Retrieves the current order status from PayPal.",
    responses={
        404: {"model": ErrorResponse, "description": "Order not found"},
        422: {"model": ErrorResponse, "description": "Malformed order id"},
        **_COMMON_ERRORS,
    },
)
async def get_order(
    order_id: str = Path(pattern=ORDER_ID_PATTERN, examples=["5O190127TN364715T"]),
    service: PaymentService = Depends(get_payment_service),
) -> OrderStatusResponse:
    """Fetch the order state from PayPal."""
    return await service.get_order(order_id)
