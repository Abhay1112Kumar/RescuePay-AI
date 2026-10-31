"""Local synthetic-only verification server: no payment routes or real model calls.
Run from repository root with backend on PYTHONPATH. Never deploy.
"""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx
import uvicorn
from app.api.v1.evidence import get_explanation_provider, router
from app.core.config import Settings, get_settings
from app.db.session import Database
from app.integrations.gemini import GeminiExplanationProvider
from app.models.payment import Payment, PaymentEvent
from fastapi import FastAPI, Request

folder = Path(__file__).resolve().parents[1] / "backend" / ".local"
folder.mkdir(exist_ok=True)
db_path = folder / f"synthetic-explanation-{uuid4().hex}.db"
settings = Settings(
    _env_file=None,
    APP_ENV="development",
    LOCAL_EVIDENCE_ENABLED=True,
    GEMINI_ENABLED=False,
    DATABASE_URL=f"sqlite+aiosqlite:///{db_path}",
    LOCAL_EVIDENCE_TOKEN="synthetic-local-token",
    LOCAL_EVIDENCE_USER_ID="demo-merchant",
)
database = Database(settings.DATABASE_URL)


async def seed():
    await database.create_all()
    async with database.session_factory() as session:
        for order in ["TESTUNCERTAIN001", "TESTVALIDMODEL01", "TESTINVALIDMODEL1"]:
            payment = Payment(
                reference_id="synthetic-only",
                description="SYNTHETIC VERIFICATION ONLY",
                currency="USD",
                amount_minor=100,
                status="CAPTURE_UNCERTAIN",
                paypal_order_id=order,
            )
            session.add(payment)
            await session.flush()
            session.add(
                PaymentEvent(
                    payment_id=payment.id,
                    event_type="paypal.capture.outcome_uncertain",
                    to_status="CAPTURE_UNCERTAIN",
                    detail="SYNTHETIC ONLY",
                )
            )
        await session.commit()


asyncio.run(seed())
app = FastAPI()
app.state.database = database
app.include_router(router, prefix="/api/v1/payments")
app.dependency_overrides[get_settings] = lambda: settings


def fake_provider(request: Request):
    if "TESTUNCERTAIN001" in request.url.path:
        return None

    def handler(_):
        plan = {
            "fact_codes": ["FRESHNESS_UNKNOWN", "NOT_CONFIRMED_PAID"],
            "action_codes": ["MANUAL_RECONCILIATION"],
        }
        if "TESTINVALIDMODEL1" in request.url.path:
            plan["fact_codes"] = ["PAID"]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": json.dumps(plan)}]},
                    }
                ]
            },
        )

    return GeminiExplanationProvider(
        "synthetic-not-a-key", transport=httpx.MockTransport(handler)
    )


app.dependency_overrides[get_explanation_provider] = fake_provider
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002, access_log=False, log_level="warning")
