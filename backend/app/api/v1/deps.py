"""Dependency providers for API v1 routes."""

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import PayPalNotConfiguredError
from app.db.session import Database
from app.integrations.paypal import PayPalClient
from app.services.demo_catalog import DemoCatalog
from app.services.payables import PayableSource
from app.services.payment_service import PaymentService


def get_database(
    request: Request, settings: Settings = Depends(get_settings)
) -> Database:
    """Return the application-wide Database, creating it on first use.

    Stored on ``app.state`` so the connection pool is shared; disposed on shutdown.
    """
    database: Database | None = getattr(request.app.state, "database", None)
    if database is None:
        database = Database.from_settings(settings)
        request.app.state.database = database
    return database


async def get_db_session(
    database: Database = Depends(get_database),
) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped AsyncSession."""
    async with database.session_factory() as session:
        yield session


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


def get_payable_source() -> PayableSource | None:
    """Approved demo authority only; synthetic test authorities override this separately."""
    return DemoCatalog()


def get_payment_service(
    session: AsyncSession = Depends(get_db_session),
    paypal_client: PayPalClient = Depends(get_paypal_client),
    settings: Settings = Depends(get_settings),
    payable_source: PayableSource | None = Depends(get_payable_source),
) -> PaymentService:
    """Construct a PaymentService bound to the request session and shared PayPal client."""
    return PaymentService(
        session, paypal_client, settings, payable_source=payable_source
    )
