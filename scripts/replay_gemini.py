"""Explicit local recorded-synthetic replay. No provider/config/DB access. Never deploy."""

import asyncio
from pathlib import Path

import uvicorn
from app.schemas.evidence import EvidenceResponse
from fastapi import FastAPI, HTTPException, Response

ROOT = Path(__file__).resolve().parents[1]
recorded = EvidenceResponse.model_validate_json(
    (ROOT / "backend/.local/SMOKECOMPLETED001-real-evidence.json").read_text(
        encoding="utf-8"
    )
)
assert recorded.ai_status == "available" and recorded.evidence.state == "COMPLETED"
assert recorded.evidence.provider_freshness == "not_checked"
assert recorded.model_selection.action_codes == ("REVIEW_RECORD",)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/api/v1/payments/orders/{order_id}/evidence")
async def evidence(order_id: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if order_id == "REPLAYERROR00001":
        raise HTTPException(503, "Offline replay: deliberate test error")
    if order_id != "REPLAYRECORDED001":
        raise HTTPException(404)
    await asyncio.sleep(2)
    return recorded


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8003, access_log=False, log_level="warning")
