"""All model traffic is MockTransport; fixture selections are not real AI."""

import asyncio
import json

import httpx
import pytest

from app.api.v1.evidence import get_explanation_provider
from app.integrations.gemini import GeminiExplanationProvider, GeminiUnavailable
from app.services.explanation import explain_payment
from tests.conftest import SAMPLE_ORDER_ID, make_settings
from tests.test_evidence import seed

PLAN = {
    "fact_codes": ["FRESHNESS_UNKNOWN", "NOT_CONFIRMED_PAID"],
    "action_codes": ["MANUAL_RECONCILIATION"],
}


def envelope(plan=PLAN):
    return {
        "candidates": [
            {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(plan)}]}}
        ]
    }


async def test_request_redaction_model_schema_and_readonly_result(db_session):
    payment = await seed(db_session)
    evidence = (await explain_payment(db_session, SAMPLE_ORDER_ID)).evidence
    requests = []

    def handler(request):
        requests.append(request)
        body = json.loads(request.content)
        assert "SECRET" not in request.content.decode()
        assert SAMPLE_ORDER_ID not in request.content.decode()
        assert payment.id not in request.content.decode()
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.url.query == b""
        assert "tools" not in body
        assert body["generationConfig"]["maxOutputTokens"] == 512
        assert body["generationConfig"]["responseJsonSchema"]["properties"][
            "action_codes"
        ]["items"]["enum"] == list(evidence.safe_actions)
        return httpx.Response(200, json=envelope())

    provider = GeminiExplanationProvider(
        "synthetic-key", transport=httpx.MockTransport(handler)
    )
    result = await explain_payment(db_session, SAMPLE_ORDER_ID, provider)
    assert result.ai_status == "available"
    assert (
        result.evidence.uncertain
        and not result.evidence.current_provider_state_verified
    )
    await db_session.refresh(payment)
    assert payment.status == "CAPTURE_UNCERTAIN" and len(requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"promptFeedback": {"blockReason": "SAFETY"}},
        {"candidates": []},
        {
            "candidates": [
                {"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{}"}]}}
            ]
        },
        envelope({"fact_codes": ["PAID"], "action_codes": []}),
        envelope({"fact_codes": ["FRESHNESS_UNKNOWN"], "action_codes": ["CAPTURE"]}),
        envelope({"fact_codes": ["STORED_STATE"], "action_codes": []}),
        envelope({**PLAN, "summary": "Payment succeeded SECRET"}),
        envelope(
            {
                "fact_codes": ["FRESHNESS_UNKNOWN", "FRESHNESS_UNKNOWN"],
                "action_codes": [],
            }
        ),
        {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"functionCall": {"name": "capture"}}]},
                }
            ]
        },
    ],
)
async def test_invalid_provider_output_is_unavailable_preserving_facts(
    db_session, body
):
    await seed(db_session)
    provider = GeminiExplanationProvider(
        "synthetic-key",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)),
    )
    result = await explain_payment(db_session, SAMPLE_ORDER_ID, provider)
    assert (
        result.ai_status == "unavailable"
        and result.evidence.state == "CAPTURE_UNCERTAIN"
    )
    assert result.model_selection is None and "SECRET" not in result.model_dump_json()


@pytest.mark.parametrize("status", [302, 400, 401, 429, 500])
async def test_http_failures_never_retry_or_expose_body(db_session, status):
    await seed(db_session)
    calls = []

    def handler(r):
        calls.append(r)
        return httpx.Response(
            status, headers={"location": "https://evil.test"}, text="SECRET"
        )

    provider = GeminiExplanationProvider(
        "synthetic-key", transport=httpx.MockTransport(handler)
    )
    result = await explain_payment(db_session, SAMPLE_ORDER_ID, provider)
    assert result.ai_status == "unavailable" and len(calls) == 1
    assert "SECRET" not in result.model_dump_json()


async def test_response_size_limit(db_session):
    await seed(db_session)
    provider = GeminiExplanationProvider(
        "synthetic-key",
        max_bytes=1024,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, content=b"x" * 5000, headers={"content-type": "application/json"}
            )
        ),
    )
    assert (
        await explain_payment(db_session, SAMPLE_ORDER_ID, provider)
    ).ai_status == "unavailable"


async def test_deadline_and_caller_cancellation_close_transport(db_session):
    await seed(db_session)
    evidence = (await explain_payment(db_session, SAMPLE_ORDER_ID)).evidence
    finished = asyncio.Event()

    async def handler(r):
        try:
            await asyncio.sleep(10)
        finally:
            finished.set()

    provider = GeminiExplanationProvider(
        "synthetic-key", timeout=0.02, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(GeminiUnavailable):
        await provider.explain(evidence)
    assert finished.is_set()
    finished.clear()
    provider = GeminiExplanationProvider(
        "synthetic-key", timeout=10, transport=httpx.MockTransport(handler)
    )
    task = asyncio.create_task(provider.explain(evidence))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()


def test_default_off_and_private_key_not_in_settings_repr():
    settings = make_settings(GEMINI_ENABLED=False, GEMINI_API_KEY="synthetic-key")
    assert get_explanation_provider(settings) is None
    assert "synthetic-key" not in repr(settings)
    assert (
        get_explanation_provider(make_settings(GEMINI_ENABLED=True, GEMINI_API_KEY=""))
        is None
    )


async def test_browser_disconnect_cancels_explanation(db_session):
    from fastapi import HTTPException, Response

    from app.api.v1.evidence import get_evidence

    await seed(db_session)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class Provider:
        async def explain(self, evidence):
            started.set()
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()

    class Request:
        async def is_disconnected(self):
            return started.is_set()

    with pytest.raises(HTTPException) as exc:
        await get_evidence(
            Response(),
            Request(),
            SAMPLE_ORDER_ID,
            db_session,
            Provider(),
            make_settings(),
        )
    assert exc.value.status_code == 499 and cancelled.is_set()


@pytest.mark.parametrize(
    "body,category,path",
    [
        ({}, "provider_blocked_or_empty", None),
        ({"candidates": [{"finishReason": "MAX_TOKENS"}]}, "truncated_output", None),
        (
            envelope({"fact_codes": ["SECRET_UNKNOWN"], "action_codes": []}),
            "unknown_ids",
            "fact_codes",
        ),
        (
            envelope(
                {"fact_codes": ["FRESHNESS_UNKNOWN"], "action_codes": ["CAPTURE"]}
            ),
            "unknown_ids",
            "action_codes",
        ),
        (
            envelope({"fact_codes": 3, "action_codes": []}),
            "schema_mismatch",
            "fact_codes",
        ),
        (
            envelope({**PLAN, "SECRET_FIELD": "buyer@example.test"}),
            "unsupported_claims",
            "$",
        ),
        (
            envelope({"fact_codes": ["STORED_STATE"], "action_codes": []}),
            "unsupported_claims",
            "fact_codes",
        ),
    ],
)
async def test_safe_failure_diagnostics(db_session, body, category, path):
    await seed(db_session)
    provider = GeminiExplanationProvider(
        "synthetic-key",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)),
    )
    result = await explain_payment(db_session, SAMPLE_ORDER_ID, provider)
    diagnostic = result.ai_diagnostic
    assert diagnostic.category == category
    assert diagnostic.elapsed_ms >= 0
    if path:
        assert path in diagnostic.validation_paths
    assert "SECRET" not in result.model_dump_json()
    assert "buyer@" not in result.model_dump_json()
    assert result.evidence.state == "CAPTURE_UNCERTAIN"


@pytest.mark.parametrize("envelope_json", [True, False])
async def test_malformed_json_stage(db_session, envelope_json):
    await seed(db_session)
    body = envelope()
    body["candidates"][0]["content"]["parts"][0]["text"] = '{"fact_codes":'
    response = httpx.Response(
        200,
        content=b"{broken" if envelope_json else json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    provider = GeminiExplanationProvider(
        "synthetic-key", transport=httpx.MockTransport(lambda r: response)
    )
    result = await explain_payment(db_session, SAMPLE_ORDER_ID, provider)
    assert result.ai_diagnostic.category == "malformed_json"
    assert result.ai_diagnostic.stage == (
        "envelope_json" if envelope_json else "plan_json"
    )


async def test_documented_signature_metadata_is_ignored(db_session):
    await seed(db_session)
    body = envelope()
    body["candidates"][0]["content"]["parts"][0].update(
        thoughtSignature="OPAQUE_SYNTHETIC", thought=False
    )
    provider = GeminiExplanationProvider(
        "synthetic-key",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)),
    )
    result = await explain_payment(db_session, SAMPLE_ORDER_ID, provider)
    assert result.ai_status == "available"
    assert "OPAQUE" not in result.model_dump_json()


async def test_timeout_has_safe_category(db_session):
    await seed(db_session)

    async def handler(request):
        await asyncio.sleep(10)

    provider = GeminiExplanationProvider(
        "synthetic-key", timeout=0.01, transport=httpx.MockTransport(handler)
    )
    result = await explain_payment(db_session, SAMPLE_ORDER_ID, provider)
    assert result.ai_diagnostic.category == "timeout"
    assert result.ai_diagnostic.stage == "http"


async def test_single_smoke_runner_cannot_spend_twice(monkeypatch, tmp_path):
    import importlib.util
    import sys
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "one_smoke", Path(__file__).resolve().parents[2] / "scripts" / "smoke_gemini.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=envelope(
                {
                    "fact_codes": ["FRESHNESS_UNKNOWN", "RECORDED_CAPTURE"],
                    "action_codes": ["REVIEW_RECORD"],
                }
            ),
        )

    monkeypatch.setattr(
        runner,
        "Settings",
        lambda: make_settings(GEMINI_ENABLED=False, GEMINI_API_KEY="synthetic-key"),
    )
    monkeypatch.setattr(runner, "FOLDER", tmp_path)
    monkeypatch.setattr(
        runner.httpx,
        "AsyncHTTPTransport",
        lambda **kwargs: httpx.MockTransport(handler),
    )
    monkeypatch.setattr(sys, "argv", ["smoke_gemini.py", "--run-one-authorized"])
    await runner.main()
    report = json.loads(
        (tmp_path / "gemini-one-retest-2026-11-01.json").read_text(encoding="utf-8")
    )
    assert report["request_count"] == 1 and report["request_limit"] == 1
    assert report["scenarios"][0]["valid"]
    assert report["scenarios"][0]["provider_metadata"]["finish_reason"] == "STOP"
    assert (
        not report["gemini_enabled_after"]
        and not report["persistent_gemini_enabled_after"]
    )
    await runner.main()
    assert len(calls) == 1


async def test_prepared_risk_runner_is_bounded_and_synthetic(monkeypatch, tmp_path):
    import importlib.util
    import sys
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "risk_smoke", Path(__file__).resolve().parents[2] / "scripts/smoke_gemini.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    calls = []

    def handler(request):
        evidence = json.loads(
            json.loads(request.content)["contents"][0]["parts"][0]["text"]
        )
        calls.append(evidence["state"])
        plan = {
            "fact_codes": ["FRESHNESS_UNKNOWN", "NOT_CONFIRMED_PAID"],
            "action_codes": ["CHECK_STATUS"],
        }
        return httpx.Response(200, json=envelope(plan))

    monkeypatch.setattr(
        runner,
        "Settings",
        lambda: make_settings(GEMINI_ENABLED=False, GEMINI_API_KEY="synthetic-key"),
    )
    monkeypatch.setattr(runner, "FOLDER", tmp_path)
    monkeypatch.setattr(
        runner.httpx,
        "AsyncHTTPTransport",
        lambda **kwargs: httpx.MockTransport(handler),
    )
    monkeypatch.setattr(
        sys, "argv", ["smoke_gemini.py", "--run-uncertain-stale-authorized"]
    )
    await runner.main()
    report = json.loads(
        (tmp_path / "gemini-risk-scenarios.json").read_text(encoding="utf-8")
    )
    assert calls == ["CAPTURE_UNCERTAIN", "APPROVED"]
    assert report["request_count"] == report["request_limit"] == 2
    assert all(s["valid"] and s["state_preserved"] for s in report["scenarios"])
    assert not report["persistent_gemini_enabled_after"]
    await runner.main()
    assert len(calls) == 2
