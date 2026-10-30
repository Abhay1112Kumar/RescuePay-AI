"""Dependency providers for API v1 routes."""

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.exceptions import PayPalNotConfiguredError
from app.integrations.paypal import PayPalClient
from app.services.payment_service import PaymentService


def get_paypal_client(
    request: Request, settings: Settings = Depends(get_settings)
) -> PayPalClient:
    """Return the application-wide PayPal client, creating it on first use.

    The client is stored on ``app.state`` so the HTTP connection pool and the
    cached access token are shared across requests. It is closed on shutdown.
    """
    if not settings.paypal_configured:
        raise PayPalNotConfiguredError()

    client: PayPalClient | None = getattr(request.app.state, "paypal_client", None)
    if client is None:
        client = PayPalClient(settings)
        request.app.state.paypal_client = client
    return client


def get_payment_service(
    paypal_client: PayPalClient = Depends(get_paypal_client),
    settings: Settings = Depends(get_settings),
) -> PaymentService:
    """Construct a PaymentService bound to the shared PayPal client."""
    return PaymentService(paypal_client, settings)
