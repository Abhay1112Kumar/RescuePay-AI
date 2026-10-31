# Read-only payment explanation foundation

Current implementation: Gemini REST adapter and a synthetic browser verification harness are now implemented. The earlier foundation-only notes below are historical where superseded by [Gemini implementation and Studio spike](gemini-implementation.md). No real Gemini verification has occurred.

## Scope and preservation

Worktree `feature/payment-explanation`, based on merged `origin/main` at `8ad32668c5c3248acefdcfc7653e519cd92665df`. Separate integration and frontend checkouts, private configuration and verification databases remain intact. No `.env` or database was copied. Existing virtualenv dependencies are reused; frontend `node_modules` remains ignored. No package dependency or SDK was added.

This implements a provider-independent read-only foundation, not real AI. The default runtime has no model adapter. The UI says AI explanation unavailable while backend facts remain usable. Templates are explicitly backend-authored, never represented as model-generated prose. Sandbox-only payment enforcement remains unchanged. This milestone makes no external AI or PayPal calls.

## Projection and trust boundaries

GET /api/v1/payments/orders/{order_id}/evidence reads a single database SELECT snapshot joining the existing payment and its audit events. It does not use PaymentService or PayPalClient, refresh provider status, capture, reconcile, commit or mutate payment state. No migration is needed. Input order identity is used only for lookup and omitted from the projected evidence/model input.

Output includes stored state, amount/currency, observation and record-update timestamps, uncertain flag, latest bounded audit window (50 rows), allowlisted event codes/state/timestamps, backend-authored facts and safe suggestion codes. Unknown events are omitted, and truncation is explicit. Raw event detail, last_error, descriptions, reference/order/payment/capture/request IDs, debug IDs, provider payloads, credentials and buyer data are never projected. Historical success may be explained from the existing verified capture record; a completed record missing capture identity is flagged uncertain for manual reconciliation.

Freshness is deliberately conservative: source=stored_backend_record, provider_freshness=not_checked, current_provider_state_verified=false. record_updated_at is not treated as a provider-check timestamp. Even recently updated COMPLETED evidence cannot prove absence of later refunds/disputes. Old audit timestamps remain visible and are not relabeled fresh. Observation time means projection time only. Browser cancellation is not stored as provider VOIDED and is never inferred from these audit records. A backend fact explicitly explains that distinction.

Backend safe suggestion codes:

| Code | Meaning |
| --- | --- |
| CHECK_STATUS | Check status separately; the existing payment-status endpoint may contact PayPal when deliberately used |
| WAIT | Wait for a pending capture; do not repeat capture |
| MANUAL_RECONCILIATION | Resolve uncertain/inconsistent evidence before new payment operations |
| REVIEW_RECORD | Review historical state; later refund/dispute state is outside this snapshot |

The panel renders suggestions as text, not executable controls. It cannot authorize captures, refunds, price changes, replacement purchases or independent success. Backend rules determine allowed codes; a model cannot add codes or change state/money.

## Local gate and setup

LOCAL_EVIDENCE_ENABLED=false is the only new setting. The endpoint requires explicit true, APP_ENV=development, a loopback peer and Host, a loopback Origin when supplied, and no Forwarded/X-Forwarded-For/X-Forwarded-Host headers. Otherwise it returns 404 before exposing evidence. Success has Cache-Control: no-store. No provider credentials are required for this read-only route.

These are development exposure guards, not authentication or ownership. Bind backend and Vite to 127.0.0.1 only; never tunnel, reverse-proxy publicly or deploy this unauthenticated application. Loopback proxy access cannot establish merchant ownership. Authentication/authorization must be designed before public use. The gate intentionally rejects forwarding proxies that supply those headers.

For optional local use configure LOCAL_EVIDENCE_ENABLED=true and APP_ENV=development privately in this new worktree's backend configuration and point DATABASE_URL at the deliberately selected local evidence database. Keep the original database/configuration intact; no migration/reset is needed. No model keys/endpoint are configured by this milestone. Existing Checkout mounts the panel only for its saved order; do not create a payment merely to view the panel. Test fixtures remain synthetic and are not application payment records.

## Provider-independent explanation interface

ExplanationProvider.explain(PaymentEvidence) receives a detached sanitized projection only. No payment repository, session, secret, raw payload or tool/action interface is provided. Its return value is untrusted and validated with extra fields forbidden:

```json
{"fact_codes":["STORED_STATE","FRESHNESS_UNKNOWN"],"action_codes":["CHECK_STATUS"]}
```

A plan may select only existing fact codes and backend-approved action codes; duplicates, unsupported actions/claims, empty observations, raw strings or additional prose/state/money fields are rejected. Exceptions and the two-second await timeout produce unavailable AI with intact facts; error details never reach the client. There is no fallback pretending to be AI. Successful injected test adapters select fact references only. The UI labels their text as backend-authored, not model-generated prose. The HTTP route currently always uses provider=None, so production-like provider availability is not claimed.

This deliberately does not support free-form model explanations yet. Structured grounding is the safe interface boundary for the next model integration. A model's output is never payment evidence. Future prose would require a separately reviewed contract, factuality safeguards and adversarial tests.

## Exact requirements for the next provider milestone

Choose a provider/model and approve its data-retention policy/cost/access. It must support asynchronous structured JSON output or an adapter that validates the exact plan schema; no tools/function execution, browsing, payment access or autonomous actions. Require bounded response size, schema/enum constraints, timeout/cancellation, sanitized failures and no raw request/response logging. Async adapters must cooperate with cancellation; CPU-bound/blocking adapters are outside this interface. Validate hallucinated state/success/actions, prompt injection and unavailable-provider behavior with mocked tests before external calls.

The future adapter will need a private backend API credential, approved provider endpoint, explicit model identifier, timeout/token or response-size budget, and retention/logging policy. No environment-variable names for those undecided provider settings are invented here. They must not be VITE_ values. The adapter must be explicitly wired into the read-only route and still receive only the sanitized evidence. No SDK, provider credential, external call or payment tool is implemented now. Public exposure additionally requires authenticated merchant ownership and access controls.

## Actual validation

- Backend pytest: 217 passed (24 new evidence cases); one existing Starlette/httpx deprecation warning.
- Backend Ruff lint and format checks: passed.
- Frontend lint/build: passed without lint warnings.
- Frontend test:evidence: 5 passed; test:checkout: 31 passed; test:health: 14 passed. Node's existing experimental TypeScript-stripping warning remains.
- Provider traffic is synthetic MockTransport only; a validation-only socket guard rejects non-loopback connections. API tests use real ASGI routing with in-memory/test SQLite and no provider dependency.
- Tests cover redaction, preserved payment state, old audit timestamps/freshness unknown, uncertain/pending/terminal states, missing capture inconsistency, bounded event windows, invalid/hallucinated model plans, provider exceptions, local gate rejection, GET-only transport and unavailable AI.
- No real-browser panel walkthrough or actual model output is claimed. No external AI/PayPal calls, existing-database migration, commits, pushes, merges, deployment or submission occurred.
