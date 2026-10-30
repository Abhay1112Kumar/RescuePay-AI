"""Pydantic schemas for payment operations (request validation and response contracts).

These models define the API contract documented in ``docs/api-contract.md``.
Monetary values are handled as ``Decimal`` internally and serialized as strings,
matching PayPal's own representation and avoiding float rounding.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.payment_state import PaymentStatus

# PayPal order ids are 17 upper-case alphanumeric characters today; allow a
# slightly wider range so a format change on PayPal's side does not break us.
ORDER_ID_PATTERN = r"^[A-Za-z0-9]{10,32}$"
REFERENCE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$"


class CreateOrderRequest(BaseModel):
    """Payload to initiate a PayPal checkout order."""

    model_config = ConfigDict(str_strip_whitespace=True)

    reference_id: str = Field(
        pattern=REFERENCE_ID_PATTERN,
        description="Caller-supplied identifier for the thing being paid for.",
        examples=["RESCUE-1001"],
    )
    currency: str = Field(
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code.",
        examples=["USD"],
    )
    amount: Decimal = Field(
        gt=0,
        max_digits=10,
        decimal_places=2,
        description="Amount with at most two decimal places.",
        examples=["25.00"],
    )
    description: str | None = Field(
        default=None,
        max_length=127,
        description="Short description shown to the buyer on PayPal.",
        examples=["Emergency donation / aid payment"],
    )

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        value = value.upper()
        if not value.isalpha():
            raise ValueError("currency must be three letters")
        return value


class MoneyAmount(BaseModel):
    """Monetary amount in PayPal's string representation."""

    currency_code: str = Field(examples=["USD"])
    value: str = Field(examples=["25.00"])


class OrderLink(BaseModel):
    """HATEOAS link returned by PayPal (the ``approve`` link is the one to follow)."""

    href: str
    rel: str
    method: str = "GET"


class OrderResponse(BaseModel):
    """Response for a newly created order."""

    order_id: str = Field(
        description="PayPal order id. Use it for status and capture calls.",
        examples=["5O190127TN364715T"],
    )
    payment_id: str = Field(
        description="RescuePay internal payment id (UUID).",
        examples=["0d0c7a2e-3f52-4b6f-9d8e-3a1c6c0f5e21"],
    )
    status: PaymentStatus = Field(examples=["CREATED"])
    request_id: str = Field(
        description="Idempotency key sent to PayPal for order creation."
    )
    links: list[OrderLink]


class OrderStatusResponse(BaseModel):
    """Current state of a payment, combining the backend record and PayPal."""

    order_id: str
    payment_id: str
    reference_id: str
    status: PaymentStatus = Field(
        description="RescuePay internal status. Only COMPLETED means funds were captured."
    )
    paypal_status: str | None = Field(
        default=None,
        description="Raw PayPal order status from the latest lookup, if available.",
        examples=["APPROVED"],
    )
    amount: MoneyAmount
    capture_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CaptureResponse(BaseModel):
    """Result of a capture request."""

    order_id: str
    payment_id: str
    capture_id: str | None = Field(
        default=None,
        description="PayPal capture id, present once PayPal accepted the capture.",
    )
    status: PaymentStatus = Field(
        description="COMPLETED when funds are captured; CAPTURE_PENDING when PayPal is still settling."
    )
    amount: MoneyAmount


class ErrorResponse(BaseModel):
    """Standard error envelope (documented for OpenAPI; produced by error handlers)."""

    detail: str | list
    error_code: str
    timestamp: datetime
    paypal_debug_id: str | None = None
