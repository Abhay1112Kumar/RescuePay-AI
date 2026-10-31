"""Backend price authority interface. Test authorities remain separate."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class Payable:
    reference_id: str
    currency: str
    amount: Decimal
    description: str | None = None


class PayableSource(Protocol):
    def resolve(self, reference_id: str) -> Payable:
        """Return a backend-authorized payable or raise PaymentValidationError."""
