"""Pydantic schemas for payment operations."""

try:
    from pydantic import BaseModel
except ImportError:

    class BaseModel:  # type: ignore[no-redef]
        pass


class PaymentBase(BaseModel):
    """Base payment schema placeholder."""

    pass
