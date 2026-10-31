# RescuePay-AI API contract

Current verification: actual USD 1.00 Sandbox checkout and a separate cancellation return are verified against the frontend evidence, backend records and audit transitions. Independent seller PayPal Dashboard comparison of capture identity, internal payment ID, amount/currency, status and timestamp is complete; see the final checkout evidence. Historical setup/blocker notes below describe earlier stages. Authentication, verified webhooks, AI and the other documented limits remain unresolved. See [checkout evidence](sandbox-checkout.md).

Correctness revision: 2026-10-31, based on Chetan's Phase 3 contract and implementation. React/TypeScript and FastAPI remain the stack. Backend-priced Sandbox demo checkout is implemented with an explicit opt-in/configuration gate; real provider verification is pending. See [checkout verification](sandbox-checkout.md) and [prior correctness evidence](backend-correctness.md).

## Base configuration and compatibility changes

- Base path `/api/v1`; JSON requests/responses. Default backend port 8000; isolated health verification uses backend 8001 and frontend 5174 through Vite.
- **New requirement:** creation requires a UUID `Idempotency-Key` header. Generate it once per deliberate operation and retain it across network/response failures; never replace it on automatic retry.
- **New response field:** status lookup includes `provider_refreshed`.
- **New states:** `CREATION_UNCERTAIN`, `CAPTURE_UNCERTAIN`. Uncertainty is no longer reset to `APPROVED` or documented as safe-to-retry `504`.
- Public creation accepts only item_id. The backend DemoCatalog resolves fixed USD price/description; caller monetary fields are rejected (422). The legacy monetary schema remains internal to the service and synthetic tests, not a public API.
- Create/capture require SANDBOX_CHECKOUT_ENABLED=true, private Sandbox client credentials, expected merchant, valid loopback callbacks and the required DB columns. Otherwise 503 SANDBOX_CHECKOUT_UNAVAILABLE. Configuration readiness does not prove provider connectivity.
- Authentication/ownership is absent. Do not expose these development payment routes publicly or claim merchant isolation.

## Errors

```json
{"detail":"Sanitized error description","error_code":"ERROR_CODE","timestamp":"2026-10-31T00:00:00Z"}
```

`detail` is a string or a schema-error array with `loc`, `msg`, `type`. Raw input and validator exception context are omitted. `paypal_debug_id` is optional. HTTP 200/201 alone never means paid.

| Status | Relevant codes |
| --- | --- |
| 400 | PAYMENT_VALIDATION_FAILED: currency/limit, unknown or mismatched authoritative payable |
| 404 | ORDER_NOT_FOUND: no local record; RESOURCE_NOT_FOUND |
| 409 | IDEMPOTENCY_CONFLICT, ORDER_CREATION_UNCERTAIN, CAPTURE_OUTCOME_UNCERTAIN, CAPTURE_IN_PROGRESS, ORDER_NOT_APPROVED, PAYMENT_INSTRUMENT_DECLINED, PAYMENT_VERIFICATION_FAILED, AMOUNT_MISMATCH, PAYMENT_INVALID_STATE |
| 422 | REQUEST_VALIDATION_ERROR |
| 502 | PAYPAL_AUTH_FAILED, PAYPAL_API_ERROR |
| 503 | SANDBOX_CHECKOUT_UNAVAILABLE, PAYPAL_NOT_CONFIGURED, PAYABLES_NOT_CONFIGURED |
| 504 | PAYPAL_TIMEOUT; never proof that a financial operation did not happen |
| 500 | INTERNAL_ERROR |

## GET /health

No body/provider credentials required. HTTP 200:

```json
{"status":"ok","service":"RescuePay-AI","version":"0.2.0"}
```

Service name is configurable. No database/provider readiness check; this cannot enable checkout.

## GET /sandbox/catalog

No provider call or secret output. Example with missing private setup:

```json
{
  "mode":"sandbox", "demo":true,
  "checkout_available":false,
  "blocking_reasons":["SANDBOX_CHECKOUT_DISABLED","PAYPAL_NOT_CONFIGURED","MERCHANT_NOT_CONFIGURED"],
  "return_origin":"http://127.0.0.1:5174",
  "items":[
    {"item_id":"demo-notebook-v1","name":"Demo notebook","amount":{"currency_code":"USD","value":"1.00"}},
    {"item_id":"demo-stickers-v1","name":"Demo sticker pack","amount":{"currency_code":"USD","value":"2.50"}}
  ]
}
```

Other blockers: RETURN_URLS_INVALID, DATABASE_NOT_READY. Missing/invalid callback configuration yields null return_origin. Both callbacks must share a loopback HTTP(S) origin, with exact /payment/return and /payment/cancel paths and no credentials/query/fragment. The frontend requires this origin to equal its own. The schema check verifies required columns, not migration history/constraints or provider reachability; run Alembic explicitly. The catalog is a local demo authority, not final merchant business pricing.

## POST /payments/orders

Required header: `Idempotency-Key: <UUID>`.

Public request (extra fields are forbidden):

```json
{"item_id":"demo-notebook-v1"}
```

Stable item IDs match `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`; unknown IDs return 400. The backend resolves catalog reference, USD amount and description. Frontend prices are display-only. Internal monetary assertions remain in service tests, using a separate synthetic PayableSource override.

HTTP 201:

```json
{
  "order_id":"5O190127TN364715T",
  "payment_id":"0d0c7a2e-3f52-4b6f-9d8e-3a1c6c0f5e21",
  "status":"CREATED",
  "request_id":"9b1f3c2e-7d4a-4e8b-a1c2-5f6e7d8c9b0a",
  "links":[{"href":"https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T","rel":"approve","method":"GET"}]
}
```

`request_id` is the backend's provider key, not the caller's header. Same header plus same normalized request replays the persisted result without another provider POST, including after session restart. Payload conflicts return 409. Concurrent callers share the unique persisted key; a running attempt may return ORDER_CREATION_UNCERTAIN.

Timeout/ambiguous error/malformed response/unsafe approval link does not authorize a new order. CREATION_UNCERTAIN remains blocked for manual/provider reconciliation. Automatic creation recovery is not implemented: provider-key retention is finite. This is per-operation idempotency, not one purchase per invoice; different keys represent different operations.

Only validated approve/payer-action links on HTTPS www.sandbox.paypal.com with the expected token may be followed. The frontend must validate links/status at runtime. Frontend /payment/return and /payment/cancel handlers bind the callback token to saved session identity before status lookup/capture. Unknown, missing or duplicate return tokens fail closed. Redirect, token or PayerID is never proof of payment.

## GET /payments/orders/{order_id}

Path pattern: `^[A-Za-z0-9]{10,32}$`. HTTP 200:

```json
{
  "order_id":"5O190127TN364715T",
  "payment_id":"0d0c7a2e-3f52-4b6f-9d8e-3a1c6c0f5e21",
  "reference_id":"REFERENCE-ID",
  "status":"APPROVED",
  "paypal_status":"APPROVED",
  "provider_refreshed":true,
  "amount":{"currency_code":"USD","value":"25.00"},
  "capture_id":null,
  "created_at":"2026-10-31T00:00:00Z",
  "updated_at":"2026-10-31T00:00:00Z"
}
```

Status is the internal enum. provider_refreshed true means this request obtained acceptable provider identity/money evidence, not that funds are captured. Failed/skipped/invalid refreshes and discarded stale concurrent results have false. Provider status and capture ID are nullable. Terminal records normally use the stored result without refreshing provider refund/dispute state.

| Status | Frontend treatment |
| --- | --- |
| CREATED | Await approval |
| APPROVED | Approved, not paid |
| CAPTURING | Wait/check status; prevent duplicate submission |
| CAPTURE_PENDING | Processing, not paid |
| CAPTURE_UNCERTAIN | Unresolved; check status, never blindly retry capture/create |
| COMPLETED | Only paid state; requires verified full capture evidence |
| FAILED / VOIDED | No success; do not automatically create a new payment |

PENDING/CREATION_UNCERTAIN describe creation records before a usable response; replay reports 409 when no stored order/approval is available.

## POST /payments/orders/{order_id}/capture

No body required; {} is accepted. Before dispatch, require an authoritative payable, verify order ID/intent, merchant, reference/custom ID and amount/currency, acquire a versioned conditional lock and persist a stable capture request ID.

HTTP 200 shape:

```json
{
  "order_id":"5O190127TN364715T",
  "payment_id":"0d0c7a2e-3f52-4b6f-9d8e-3a1c6c0f5e21",
  "capture_id":"1JS80234KJ293810L",
  "status":"COMPLETED",
  "amount":{"currency_code":"USD","value":"25.00"}
}
```

Only matching single full capture details with a nonempty ID, matching money, final_capture true, explicit capture COMPLETED and matching order/merchant identity establish success. Top-level order status is insufficient. Split/partial capture is unsupported. Other 200 states can be CAPTURE_PENDING, CAPTURE_UNCERTAIN or FAILED; inspect validated status, never HTTP status alone.

Unknown failure/timeout persists uncertainty before GET reconciliation. Verified completed/pending evidence may resolve it; otherwise return 409 CAPTURE_OUTCOME_UNCERTAIN. Repeated capture on an uncertain record only checks status, never dispatches another capture POST. Known ORDER_NOT_APPROVED/PAYER_ACTION_REQUIRED or INSTRUMENT_DECLINED permits explicit buyer action, not automatic background retry.

Nonexpired CAPTURING returns 409 CAPTURE_IN_PROGRESS. Lease expiry (120 seconds by default) converts it to uncertain for GET reconciliation, never another charge. Optimistic versions discard stale lookup/owner writes. Unique provider identifiers prevent assigning one capture to two records.

## Webhooks and remaining limits

POST /webhooks/paypal is planned and absent. No webhook signature/deduplication guarantee exists. Authentication/ownership, automatic creation reconciliation, refunds, transaction list/metrics, public hosting and AI are outside this milestone. The full demo checkout UI is implemented and mocked; real Sandbox verification is pending.

Provider semantics were checked against [Orders v2](https://developer.paypal.com/api/orders/v2) and [PayPal idempotency](https://developer.paypal.com/api/rest/reference/idempotency/). Provider retention is bounded; it cannot replace durable state and reconciliation. Real Sandbox checkout verification is pending.


## GET /payments/orders/{order_id}/evidence (local development only)

Default-off LOCAL_EVIDENCE_ENABLED gate plus development/loopback restrictions. No public audit/list endpoint or model provider is enabled. 404 when gated/unknown order; path pattern matches the existing order lookup; 200 has Cache-Control: no-store. No PayPal calls or writes.

Response: {evidence, ai_status, ai_reason, model_selection}. Evidence includes state, amount, observed_at, record_updated_at, source="stored_backend_record", provider_freshness="not_checked", current_provider_state_verified=false, uncertain, events_truncated, events[{code,state,recorded_at}], facts[{code,text}], safe_actions[]. Identifiers and all arbitrary details/PII/provider payloads are excluded. Current runtime always returns ai_status="unavailable", ai_reason="provider_not_configured", model_selection=null. Facts/suggestions are backend-authored, not AI. Future injected structured plans cannot add actions or override facts. Exact bounds, safe codes, local setup and provider contract: [payment explanation foundation](payment-explanation.md).


### Gemini adapter update

The local evidence route can now inject the Gemini REST adapter only when GEMINI_ENABLED=true and a private GEMINI_API_KEY is configured. Default remains unavailable. GET is read-only with respect to payment state; when explicitly enabled it can incur a model request, so do not treat it as a free provider probe. The model selects/orders grounded fact/action IDs only; no model-authored payment claims or free-form prose is accepted. API schema remains evidence/ai_status/ai_reason/model_selection. Configured failures, response truncation/limits, invalid JSON/IDs/claims and timeouts return unavailable AI with original facts. Client disconnect cancels explanation processing (499 if still observable). Configure deadlines at most 20 seconds; frontend evidence deadline is 25 seconds. See [implementation and private setup](gemini-implementation.md). Authentication remains absent and local guards remain mandatory.


Evidence diagnostics (local-only): unavailable AI may include optional ai_diagnostic with an allowlisted category/stage, elapsed_ms, sanitized finish_reason and validation_paths ($, fact_codes, action_codes only). This additive field contains no provider body, selected unknown IDs, exception messages or credentials. Verified evidence and payment state retain their existing semantics. See gemini-implementation.md for categories and offline diagnosis.
### Local authentication boundary

The local evidence route requires the development/loopback gate plus `Authorization: Bearer <LOCAL_EVIDENCE_TOKEN>` and `X-RescuePay-Local-User` matching `LOCAL_EVIDENCE_USER_ID`; missing or mismatched identity returns 401. Only synthetic/demo reference namespaces are eligible. This is not production identity management; local guards remain mandatory.
