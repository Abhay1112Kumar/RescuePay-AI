"""Default-off loopback development projection, not an authenticated public API."""

import asyncio
from ipaddress import ip_address
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db_session
from app.core.config import Settings, get_settings
from app.integrations.gemini import GeminiExplanationProvider
from app.schemas.evidence import EvidenceResponse
from app.schemas.payment import ORDER_ID_PATTERN
from app.services.explanation import ExplanationProvider, explain_payment

router = APIRouter()


def require_local_evidence(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    def loopback(host: str | None) -> bool:
        try:
            return bool(host) and (host == "localhost" or ip_address(host).is_loopback)
        except ValueError:
            return False

    origin = request.headers.get("origin")
    if (
        not settings.LOCAL_EVIDENCE_ENABLED
        or settings.APP_ENV != "development"
        or not request.client
        or not loopback(request.client.host)
        or not loopback(request.url.hostname)
        or any(
            key in request.headers
            for key in ("forwarded", "x-forwarded-for", "x-forwarded-host")
        )
        or (origin and not loopback(urlsplit(origin).hostname))
    ):
        raise HTTPException(status_code=404, detail="Local evidence unavailable")


def get_explanation_provider(
    settings: Settings = Depends(get_settings),
) -> ExplanationProvider | None:
    if not settings.GEMINI_ENABLED or not settings.GEMINI_API_KEY.get_secret_value():
        return None
    return GeminiExplanationProvider(
        settings.GEMINI_API_KEY.get_secret_value(),
        settings.GEMINI_MODEL,
        settings.GEMINI_TIMEOUT_SECONDS,
        settings.GEMINI_MAX_RESPONSE_BYTES,
    )


@router.get(
    "/orders/{order_id}/evidence",
    response_model=EvidenceResponse,
    dependencies=[Depends(require_local_evidence)],
)
async def get_evidence(
    response: Response,
    request: Request,
    order_id: str = Path(pattern=ORDER_ID_PATTERN),
    session: AsyncSession = Depends(get_db_session),
    provider: ExplanationProvider | None = Depends(get_explanation_provider),
    settings: Settings = Depends(get_settings),
) -> EvidenceResponse:
    response.headers["Cache-Control"] = "no-store"

    async def wait_for_disconnect():
        while not await request.is_disconnected():
            await asyncio.sleep(0.05)

    work = asyncio.create_task(
        explain_payment(
            session, order_id, provider, timeout=settings.GEMINI_TIMEOUT_SECONDS + 0.5
        )
    )
    disconnected = asyncio.create_task(wait_for_disconnect())
    try:
        done, _ = await asyncio.wait(
            {work, disconnected}, return_when=asyncio.FIRST_COMPLETED
        )
        if disconnected in done:
            raise HTTPException(status_code=499, detail="Request cancelled")
        return await work
    finally:
        for task in (work, disconnected):
            if not task.done():
                task.cancel()
        await asyncio.gather(work, disconnected, return_exceptions=True)
