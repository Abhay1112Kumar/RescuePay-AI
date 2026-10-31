"""Approved, backend-owned Sandbox demo catalog; not merchant production prices.

Identifiers/prices are stable. Introduce a new identifier for a new price.
No quantities, discounts or caller-provided monetary values are accepted.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.exceptions import PaymentValidationError
from app.services.payables import Payable


@dataclass(frozen=True)
class DemoItem:
    item_id: str
    name: str
    price: Decimal


DEMO_ITEMS = (
    DemoItem("demo-notebook-v1", "Demo notebook", Decimal("1.00")),
    DemoItem("demo-stickers-v1", "Demo sticker pack", Decimal("2.50")),
)


class DemoCatalog:
    def resolve(self, reference_id: str) -> Payable:
        item = next((item for item in DEMO_ITEMS if item.item_id == reference_id), None)
        if item is None:
            raise PaymentValidationError("Unknown Sandbox demo item.")
        return Payable(
            item.item_id, "USD", item.price, f"Sandbox demo only: {item.name}"
        )
