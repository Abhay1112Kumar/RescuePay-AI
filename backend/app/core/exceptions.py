"""Domain exceptions mapped to sanitized HTTP error responses.

Every exception carries an HTTP status code, a stable machine-readable error code,
and a human-readable detail that is safe to return to API clients. Raw provider
responses and credentials must never be placed in ``detail``.
"""


class RescuePayError(Exception):
    """Base class for all application-level errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    default_detail: str = "An internal error occurred."

    def __init__(self, detail: str | None = None, *, debug_id: str | None = None):
        self.detail = detail or self.default_detail
        # PayPal's debug_id is safe to expose and useful when contacting PayPal support.
        self.debug_id = debug_id
        super().__init__(self.detail)


class PaymentValidationError(RescuePayError):
    """Request failed a backend business rule (currency, amount limits, etc.)."""

    status_code = 400
    error_code = "PAYMENT_VALIDATION_FAILED"
    default_detail = "Payment request failed validation."


class OrderNotFoundError(RescuePayError):
    """The requested PayPal order does not exist."""

    status_code = 404
    error_code = "ORDER_NOT_FOUND"
    default_detail = "Order not found."


class PayPalNotConfiguredError(RescuePayError):
    """PayPal credentials are missing; payment endpoints cannot operate."""

    status_code = 503
    error_code = "PAYPAL_NOT_CONFIGURED"
    default_detail = "Payment provider is not configured."


class PayPalAuthError(RescuePayError):
    """PayPal rejected the client credentials or the access token."""

    status_code = 502
    error_code = "PAYPAL_AUTH_FAILED"
    default_detail = "Authentication with the payment provider failed."


class PayPalAPIError(RescuePayError):
    """PayPal returned an unexpected error or was unreachable."""

    status_code = 502
    error_code = "PAYPAL_API_ERROR"
    default_detail = "The payment provider returned an error."

    def __init__(
        self,
        detail: str | None = None,
        *,
        debug_id: str | None = None,
        paypal_status: int | None = None,
        paypal_name: str | None = None,
    ):
        super().__init__(detail, debug_id=debug_id)
        self.paypal_status = paypal_status
        self.paypal_name = paypal_name


class PayPalTimeoutError(PayPalAPIError):
    """PayPal did not respond within the configured timeout."""

    status_code = 504
    error_code = "PAYPAL_TIMEOUT"
    default_detail = "The payment provider did not respond in time."
