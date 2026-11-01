"""Explicitly authorized, synthetic-only real smoke runner; never auto-retries.
Run from repository root, backend on PYTHONPATH. Repeated runs fail closed if a
ledger already contains attempts. No credentials, model payloads or PII logged.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from uuid import uuid4

import httpx
from app.api.v1.evidence import get_explanation_provider, router
from app.core.config import Settings, get_settings
from app.db.session import Database
from app.models.payment import Payment, PaymentEvent
from fastapi import FastAPI

logging.disable(logging.CRITICAL)
ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "backend" / ".local"
LEDGER = FOLDER / "gemini-authorized-smoke.json"


async def main():
    risk = "--run-uncertain-stale-authorized" in sys.argv
    single = "--run-one-authorized" in sys.argv
    ledger = (
        FOLDER / "gemini-risk-scenarios.json"
        if risk
        else FOLDER / "gemini-one-retest-2026-11-01.json"
        if single
        else LEDGER
    )
    if "--run-authorized" not in sys.argv and not single and not risk:
        print("No request sent: explicit --run-authorized required.")
        return
    settings = Settings(_env_file=os.getenv("RESCUEPAY_PRIVATE_ENV_FILE") or None)
    if settings.GEMINI_ENABLED:
        print("No request sent: disable persistent Gemini configuration first.")
        return
    if not settings.GEMINI_API_KEY.get_secret_value():
        print("No request sent: private Gemini configuration unavailable.")
        return
    FOLDER.mkdir(exist_ok=True)
    if ledger.exists() and (
        single
        or risk
        or json.loads(ledger.read_text(encoding="utf-8")).get("request_count", 0)
    ):
        print(
            "No request sent: prior attempt ledger exists; new authorization/review required."
        )
        return
    report = {
        "model": settings.GEMINI_MODEL,
        "request_count": 0,
        "halted": False,
        "scenarios": [],
        "gemini_enabled_after": False,
        "persistent_gemini_enabled_before": settings.GEMINI_ENABLED,
        "request_limit": 2 if risk else 1 if single else 3,
    }

    if single or risk:
        # Exclusive durable claim: even a crashed/parallel run cannot spend twice.
        with ledger.open("x", encoding="utf-8") as claim:
            json.dump(report, claim)

    def save():
        ledger.write_text(json.dumps(report, indent=2), encoding="utf-8")

    settings.GEMINI_ENABLED = True
    settings.APP_ENV = "development"
    settings.LOCAL_EVIDENCE_ENABLED = True
    settings.LOCAL_EVIDENCE_TOKEN = "synthetic-local-token"
    settings.LOCAL_EVIDENCE_USER_ID = "demo-merchant"
    settings.DATABASE_AUTO_CREATE = False
    settings.DATABASE_URL = f"sqlite+aiosqlite:///{FOLDER / ('real-smoke-synthetic-' + uuid4().hex + '.db')}"
    database = Database(settings.DATABASE_URL)
    transport = httpx.AsyncHTTPTransport(retries=0)

    class BudgetTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if (
                report["halted"]
                or report["request_count"] >= report["request_limit"]
                or str(request.url)
                != f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent"
            ):
                raise RuntimeError("Smoke budget/target rejected")
            report["request_count"] += 1
            save()
            response = await transport.handle_async_request(request)
            report["last_http_status"] = response.status_code
            if response.status_code != 200:
                report["halted"] = True
            save()
            return response

    provider = get_explanation_provider(settings)
    provider._transport = BudgetTransport()
    application = FastAPI()
    application.state.database = database
    application.include_router(router, prefix="/api/v1/payments")
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_explanation_provider] = lambda: provider
    scenarios = [("SMOKECOMPLETED001", "COMPLETED", 0)]
    if risk:
        scenarios = []
    if not single:
        scenarios += [
            ("SMOKEUNCERTAIN001", "CAPTURE_UNCERTAIN", 0),
            ("SMOKESTALE000001", "APPROVED", 7),
        ]
    try:
        await database.create_all()
        async with database.session_factory() as session:
            for order, state, days in scenarios:
                payment = Payment(
                    reference_id="SYNTHETIC-SMOKE",
                    description="SYNTHETIC ONLY",
                    currency="USD",
                    amount_minor=100,
                    status=state,
                    paypal_order_id=order,
                    paypal_capture_id="SYNTHETIC-CAPTURE"
                    if state == "COMPLETED"
                    else None,
                    updated_at=datetime.now(UTC) - timedelta(days=days),
                )
                session.add(payment)
                await session.flush()
                session.add(
                    PaymentEvent(
                        payment_id=payment.id,
                        event_type="paypal.capture.completed"
                        if state == "COMPLETED"
                        else "paypal.capture.outcome_uncertain"
                        if state == "CAPTURE_UNCERTAIN"
                        else "paypal.order.approved",
                        to_status=state,
                        created_at=datetime.now(UTC) - timedelta(days=days),
                    )
                )
            await session.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application, client=("127.0.0.1", 123)),
            base_url="http://localhost",
        ) as client:
            for order, state, _ in scenarios:
                started = monotonic()
                result = await client.get(
                    f"/api/v1/payments/orders/{order}/evidence",
                    headers={
                        "Authorization": "Bearer synthetic-local-token",
                        "X-RescuePay-Local-User": "demo-merchant",
                    },
                )
                body = result.json()
                valid = (
                    result.status_code == 200
                    and body.get("ai_status") == "available"
                    and body["evidence"]["state"] == state
                    and body["evidence"]["provider_freshness"] == "not_checked"
                    and body["evidence"]["current_provider_state_verified"] is False
                )
                async with database.session_factory() as session:
                    from sqlalchemy import select

                    stored = (
                        await session.execute(
                            select(Payment).where(Payment.paypal_order_id == order)
                        )
                    ).scalar_one()
                    valid = valid and stored.status == state
                report["scenarios"].append(
                    {
                        "scenario": order,
                        "valid": valid,
                        "ai_status": body.get("ai_status"),
                        "state_preserved": stored.status == state,
                        "diagnostic": body.get("ai_diagnostic"),
                        "provider_metadata": getattr(provider, "last_metadata", None),
                        "elapsed_ms": int((monotonic() - started) * 1000),
                        "model_selection": body.get("model_selection")
                        if valid
                        else None,
                    }
                )
                # Sanitized validated projection only, to replay in the browser
                # without spending any additional model requests.
                if valid:
                    (FOLDER / f"{order}-real-evidence.json").write_text(
                        json.dumps(body), encoding="utf-8"
                    )
                else:
                    report["halted"] = True
                    report["sanitized_error"] = (
                        "Provider HTTP failure"
                        if report.get("last_http_status") != 200
                        else "Model output/timeout failed runtime validation"
                    )
                save()
                if not valid:
                    break
    except Exception:  # noqa: BLE001 - suppress private transport/config details
        report["halted"] = True
        report["sanitized_error"] = "Smoke test failed; exception details suppressed"
    finally:
        settings.GEMINI_ENABLED = False
        report["gemini_enabled_after"] = settings.GEMINI_ENABLED
        report["persistent_gemini_enabled_after"] = Settings().GEMINI_ENABLED
        report["finished_at"] = datetime.now(UTC).isoformat()
        save()
        await transport.aclose()
        await database.dispose()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:  # noqa: BLE001 - suppress private transport/config details
        print(
            "No further request sent; configuration/startup failure details suppressed."
        )
