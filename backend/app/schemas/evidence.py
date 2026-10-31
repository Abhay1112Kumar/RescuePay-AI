"""Strict sanitized evidence and provider-independent explanation contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.payment import MoneyAmount
from app.services.payment_state import PaymentStatus

ActionCode = Literal["CHECK_STATUS", "WAIT", "MANUAL_RECONCILIATION", "REVIEW_RECORD"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceFact(StrictModel):
    code: str
    text: str


class EvidenceEvent(StrictModel):
    code: str
    state: PaymentStatus | None
    recorded_at: datetime


class PaymentEvidence(StrictModel):
    state: PaymentStatus
    amount: MoneyAmount
    observed_at: datetime
    record_updated_at: datetime
    source: Literal["stored_backend_record"] = "stored_backend_record"
    provider_freshness: Literal["not_checked"] = "not_checked"
    current_provider_state_verified: Literal[False] = False
    uncertain: bool
    events_truncated: bool
    events: tuple[EvidenceEvent, ...]
    facts: tuple[EvidenceFact, ...]
    safe_actions: tuple[ActionCode, ...]


class ExplanationPlan(StrictModel):
    # No free text, payment state, money or executable actions from a model.
    fact_codes: tuple[str, ...] = Field(min_length=1, max_length=8)
    action_codes: tuple[ActionCode, ...] = Field(max_length=4)


class ExplanationDiagnostic(StrictModel):
    category: Literal[
        "timeout",
        "provider_blocked_or_empty",
        "truncated_output",
        "malformed_json",
        "schema_mismatch",
        "unknown_ids",
        "unsupported_claims",
        "http_error",
        "response_limit",
        "transport_error",
    ]
    stage: Literal[
        "http",
        "envelope_json",
        "extraction",
        "plan_json",
        "schema",
        "grounding",
        "service",
    ]
    elapsed_ms: int = Field(default=0, ge=0, le=86400000)
    finish_reason: (
        Literal["STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "OTHER"] | None
    ) = None
    validation_paths: tuple[Literal["$", "fact_codes", "action_codes"], ...] = ()


class EvidenceResponse(StrictModel):
    evidence: PaymentEvidence
    ai_status: Literal["unavailable", "available"]
    ai_reason: (
        Literal["provider_not_configured", "invalid_or_unavailable_output"] | None
    ) = None
    model_selection: ExplanationPlan | None = None
    ai_diagnostic: ExplanationDiagnostic | None = None
