"""Local Sandbox configuration gate. No credentials or provider connectivity probe."""

from urllib.parse import urlsplit

from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.deps import get_database
from app.core.config import Settings, get_settings
from app.core.exceptions import CheckoutUnavailableError
from app.db.session import Database
from app.models.payment import Payment, PaymentEvent


class CheckoutReadiness(BaseModel):
    checkout_available: bool
    blocking_reasons: list[str]
    return_origin: str | None


def checkout_return_origin(settings: Settings) -> str | None:
    try:
        returned = urlsplit(settings.PAYPAL_RETURN_URL)
        cancelled = urlsplit(settings.PAYPAL_CANCEL_URL)
        for url, path in (
            (returned, "/payment/return"),
            (cancelled, "/payment/cancel"),
        ):
            if (
                url.scheme not in ("http", "https")
                or url.hostname not in ("localhost", "127.0.0.1", "::1")
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path != path
            ):
                return None
        if (returned.scheme, returned.hostname, returned.port) != (
            cancelled.scheme,
            cancelled.hostname,
            cancelled.port,
        ):
            return None
        return f"{returned.scheme}://{returned.netloc}"
    except ValueError:
        return None


async def get_checkout_readiness(
    settings: Settings = Depends(get_settings),
    database: Database = Depends(get_database),
) -> CheckoutReadiness:
    reasons = []
    if not settings.SANDBOX_CHECKOUT_ENABLED:
        reasons.append("SANDBOX_CHECKOUT_DISABLED")
    if not settings.paypal_configured:
        reasons.append("PAYPAL_NOT_CONFIGURED")
    if not settings.PAYPAL_MERCHANT_ID.strip():
        reasons.append("MERCHANT_NOT_CONFIGURED")
    origin = checkout_return_origin(settings)
    if origin is None:
        reasons.append("RETURN_URLS_INVALID")
    try:
        async with database.engine.connect() as connection:

            def schema_matches(sync_connection):
                inspector = inspect(sync_connection)
                for model in (Payment, PaymentEvent):
                    if not inspector.has_table(model.__tablename__):
                        return False
                    found = {
                        column["name"]
                        for column in inspector.get_columns(model.__tablename__)
                    }
                    if not {column.name for column in model.__table__.columns} <= found:
                        return False
                return True

            ready = await connection.run_sync(schema_matches)
    except (SQLAlchemyError, OSError):
        ready = False
    if not ready:
        reasons.append("DATABASE_NOT_READY")
    return CheckoutReadiness(
        checkout_available=not reasons, blocking_reasons=reasons, return_origin=origin
    )


async def require_checkout(
    readiness: CheckoutReadiness = Depends(get_checkout_readiness),
) -> None:
    if not readiness.checkout_available:
        raise CheckoutUnavailableError()
