"""Real application demo catalog; no payment/provider calls and no synthetic records."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.checkout import CheckoutReadiness, get_checkout_readiness
from app.schemas.payment import MoneyAmount
from app.services.demo_catalog import DEMO_ITEMS

router = APIRouter()


class CatalogItem(BaseModel):
    item_id: str
    name: str
    amount: MoneyAmount


class CatalogResponse(CheckoutReadiness):
    mode: str = "sandbox"
    demo: bool = True
    items: list[CatalogItem]


@router.get("/catalog", response_model=CatalogResponse)
async def get_catalog(
    readiness: CheckoutReadiness = Depends(get_checkout_readiness),
) -> CatalogResponse:
    return CatalogResponse(
        **readiness.model_dump(),
        items=[
            CatalogItem(
                item_id=item.item_id,
                name=item.name,
                amount=MoneyAmount(currency_code="USD", value=f"{item.price:.2f}"),
            )
            for item in DEMO_ITEMS
        ],
    )
