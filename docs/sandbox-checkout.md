# Backend-priced Sandbox checkout

Current verification: actual USD 1.00 Sandbox checkout, a separate cancellation return, and independent seller Dashboard comparison of the successful capture are verified against frontend evidence, backend records, audit transitions, and provider transaction details. Historical setup/blocker notes below describe earlier stages. Gemini has exactly two synthetic validations recorded (uncertain and stale), remains disabled by default, and live browser-to-Gemini verification remains pending.

Implemented 2026-10-31 in the existing integration worktree, branch `integration/frontend-backend`, HEAD `1184c78`. Changes remain uncommitted. Existing correctness work, synthetic fixtures, documentation and skills are preserved. Main, the original frontend checkout and remote branches were not changed this milestone. Chetan's contribution is retained; Abhay owns the combined implementation.

## Scope and contract

The approved MVP is a small-merchant assistant explaining incomplete, failed or uncertain payments. Future AI reads sanitized backend-verified facts and suggests safe actions; it cannot execute payments, change prices or independently declare success. No AI endpoint is implemented here.

The backend owns a clearly labeled demo catalog, not commercial product pricing:

| Stable item ID | Demo item | Fixed price |
| --- | --- | --- |
| demo-notebook-v1 | Demo notebook | USD 1.00 |
| demo-stickers-v1 | Demo sticker pack | USD 2.50 |

A changed price needs a new item identifier. No quantities, discounts or caller monetary overrides are supported. Synthetic RESCUE/LIMIT payables remain exclusively in test overrides.

- GET `/api/v1/sandbox/catalog` returns demo items, local configuration blockers and intended callback origin. It never contacts PayPal or exposes credentials.
- POST `/api/v1/payments/orders` accepts only `{"item_id":"demo-notebook-v1"}` and a UUID `Idempotency-Key`. Backend resolution supplies price/currency/reference/description. Extra amount/currency fields return 422.
- GET `/api/v1/payments/orders/{order_id}` supplies verified status and `provider_refreshed` provenance.
- POST `/api/v1/payments/orders/{order_id}/capture` retains strict identity/full-capture checks and uncertainty rules.

See the [API contract](api-contract.md) and [prior correctness evidence](backend-correctness.md). Readiness requires explicit opt-in, credential presence, expected merchant, valid loopback callbacks and required database columns. It does not authenticate credentials or prove provider reachability, constraints or migration history. Run Alembic explicitly. Health alone never enables checkout; the frontend additionally requires the callback origin to match its exact origin.

## Frontend safety

Selection leads to creation, same-tab Sandbox approval, return/cancel handling, backend capture and verified status. Both applications restrict approval to HTTPS `www.sandbox.paypal.com/checkoutnow` with the exact bound order token.

The operation UUID/item are saved before creation; retries retain that key. Order/payment identity and validated approval URL are saved before redirect. Missing, duplicate or mismatched return tokens fail closed. PayerID is neither stored nor accepted as evidence. Only an explicit new-checkout action replaces the operation.

Capture requires a fresh backend APPROVED lookup and no prior capture attempt. Capture intent is persisted before dispatch. Timeout, reload or duplicate callback cannot trigger blind capture retry; only read-only reconciliation follows. A capture error cannot enable a replacement checkout until backend status establishes a terminal outcome. Backend locks/keys remain authoritative across concurrent callers. Cancel expresses browser intent, not provider void/payment proof. Only explicit matching COMPLETED capture evidence displays success; approval, pending, redirect and HTTP 200 do not.

Session storage retains one operation in the same tab. Do not close the tab, clear storage or replace the database while an outcome is unresolved. Lost local identity requires manual reconciliation, not another payment. Automatic ambiguous-creation recovery and invoice-level uniqueness are not implemented; different explicit keys represent separate purchases.

## Migration 0002: review before existing storage

[Migration source](../backend/alembic/versions/20261031_0002_payment_safety.py) adds nullable unique creation_key, approval_url and non-null optimistic version (default 1). Legacy COMPLETED rows become CAPTURE_UNCERTAIN with verification-upgrade audit events because old success checks were weaker. It neither fabricates verification nor captures again. Downgrade refuses unresolved uncertainty.

Stop old backend processes and back up existing storage before migrating it. Historical noncatalog records may need their original trusted payable authority plus provider evidence before re-verification; do not simply reset their status. Never run older retry logic against uncertain states.

This milestone applied 0001 then 0002 only to a new ignored disposable database: `backend/.local/sandbox-checkout-verification-4477b021ef7d4ce38293626cf68d632e.db`. Alembic current reported `0002 (head)`. Existing developer storage was not inspected or migrated. Tests also cover populated legacy quarantine and downgrade protection.

## Private Sandbox setup

No real .env contents or credentials were read. At verification time backend/.env was absent. The current validation server explicitly has blank credentials/merchant ID, checkout disabled and an outbound socket guard. Actual provider testing has not occurred.

1. Follow the official [developer setup](https://developer.paypal.com/api/get-started/) and [Sandbox accounts guidance](https://developer.paypal.com/sandbox-testing/accounts). Use **Sandbox** Apps & Credentials with a Sandbox Business seller and separate Sandbox Personal buyer. Never select Live or use real payment details.
2. Privately obtain the Sandbox app client ID/secret and seller merchant ID. The merchant ID is the seller identity from its Sandbox account settings > Business information, not the buyer PayerID or app client ID. Keep buyer login credentials private. Never paste credentials in chat or expose .env through screenshots/logs.
3. From backend/, copy the template only if private config does not exist, then edit it privately:

```powershell
if (!(Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
New-Item -ItemType Directory -Path .local -Force | Out-Null
```

Privately fill PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET and PAYPAL_MERCHANT_ID. Set these nonsecret values in the backend .env:

```dotenv
PAYPAL_MODE=sandbox
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
SANDBOX_CHECKOUT_ENABLED=true
PAYPAL_RETURN_URL=http://127.0.0.1:5174/payment/return
PAYPAL_CANCEL_URL=http://127.0.0.1:5174/payment/cancel
DATABASE_URL=sqlite+aiosqlite:///./.local/sandbox-checkout-demo.db
DATABASE_AUTO_CREATE=false
DATABASE_ECHO=false
DEBUG=false
```

Use a fresh demo database first. Review the migration before choosing existing storage, and retain the database while any payment is unresolved. Relative SQLite paths assume backend/ as working directory.

4. Stop the validation backend and start a fresh normal shell. Its blank credential overrides and validation-only PYTHONPATH guard must not carry over; environment variables override .env. Do not dump environment variables. In an inherited verification shell, remove only known task overrides without printing values:

```powershell
Remove-Item Env:PAYPAL_CLIENT_ID,Env:PAYPAL_CLIENT_SECRET,Env:PAYPAL_MERCHANT_ID,Env:SANDBOX_CHECKOUT_ENABLED,Env:DATABASE_URL,Env:PYTHONPATH -ErrorAction SilentlyContinue
```

The guard is only for mocked verification. If the agent-owned validation server still occupies 8001, tell the agent private configuration is ready so it can restart that known process. Never terminate an unrelated listener blindly.

5. From backend/, use its existing virtual environment. Create it/install declared requirements only if absent:

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic current
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

6. From frontend/, reuse existing dependencies (npm ci only if installation is needed):

```powershell
$env:RESCUEPAY_API_TARGET = 'http://127.0.0.1:8001'
npm.cmd run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Open [local Checkout](http://127.0.0.1:5174/checkout) and recheck configuration. Use exactly 127.0.0.1:5174 throughout; localhost is a different browser origin. No provider secret/token belongs in VITE_ config. Local readiness only permits a Sandbox attempt; it does not verify provider credentials.

7. Select the USD 1.00 notebook, create once and retain the displayed operation/order identity. Continue to Sandbox and sign in privately as the buyer. Approve once. On return, require matching backend order/payment identity, USD amount, explicit COMPLETED and verified capture ID. Separately test cancel/resume and read-only status refresh. Never infer success from redirect/HTTP 200. If capture is uncertain, preserve its session/database and check status only; do not create a replacement to hide uncertainty.

Provider references: [Orders v2](https://developer.paypal.com/api/orders/v2), [idempotency](https://developer.paypal.com/api/rest/reference/idempotency/). Provider retention is bounded and cannot replace durable local state. These steps use test funds exclusively.

## Actual checks

Commands ran in the integration worktree on 2026-10-31. All automated provider traffic uses synthetic fixtures/MockTransport; frontend fixtures exercise the actual adapter/controller without PayPal navigation.

| Check | Actual result |
| --- | --- |
| Backend pytest -q --tb=short | 193 passed; one existing Starlette/httpx deprecation warning |
| Backend Ruff check --no-cache . | Passed |
| Backend Ruff format --check . | Passed, 49 files |
| Backend pip check | Passed |
| Frontend npm.cmd run lint | Passed, no warning; drawer stale-ref cleanup fixed |
| Frontend npm.cmd run build | Passed |
| Frontend npm.cmd run test:health | 14 passed |
| Frontend npm.cmd run test:checkout | 31 passed |
| Fresh disposable Alembic upgrade/current | Upgraded through 0002; current 0002 (head) |
| Actual FastAPI through Vite/frontend adapters | Health connected/version 0.2.0; fixed catalog returned; three expected setup blockers; creation refused with 503 SANDBOX_CHECKOUT_UNAVAILABLE |
| Actual browser | Item selection works; connected health cannot enable create; setup reasons visible; mobile Escape restores drawer focus; catalog fits 320/390px viewports |
| Actual PayPal OAuth/order/approval/capture | Not run: credentials/merchant missing and explicit flag false |

Documentation validation passed for 12 files/52 local links, canonical instruction filename casing and skill frontmatter; git diff --check passed.

Node emits its expected experimental TypeScript-stripping warning. No dependencies were added or lockfiles changed. Tests and validation backend use an ignored non-loopback socket guard; no PayPal call occurred. Current preview shows a real configuration gate, not simulated provider success.

## Changed files in this milestone

- Backend authority/config/API: services/demo_catalog.py, payables.py, payment_service.py; api/v1/checkout.py, sandbox.py, deps.py, payments.py, router.py; core/config.py, exceptions.py; schemas/payment.py; .env.example.
- Backend tests: test_sandbox_checkout.py, test_payments_api.py, conftest.py. Earlier correctness tests/migration remain preserved.
- Frontend: api/checkout.ts, checkout/controller.ts, hooks/useSandboxCheckout.ts, components/SandboxCheckout.tsx and .css; App.tsx; vite.config.ts; package.json; tests/checkout.test.mjs.
- Instructions/docs: root/frontend AGENTS and READMEs, api-contract.md, project-context.md, product-feasibility.md, this report; historical backend-correctness.md gains a scope notice. .gitignore excludes backend/.local/ storage.

## Remaining blocker and limits

The immediate blocker is private Sandbox app credentials, seller merchant identity and explicit opt-in, then a fresh backend restart and actual buyer walkthrough. Mock checks do not prove provider credentials, account eligibility, real approval links or capture behavior.

Development routes use the documented local demo boundary and must stay local. Verified webhooks, automatic ambiguous-creation reconciliation, cross-device recovery, split capture, refunds/disputes, PostgreSQL/multi-host operation, history/metrics and deployment are outside this verification. The read-only Gemini explanation is separately documented and remains disabled by default; no autonomous payment operation exists. No commit, push, main merge, deployment or submission occurred.

## Private configuration readiness follow-up

After Abhay confirmed private configuration was saved, the known validation backend on port 8001 was stopped and restarted with task credential/DB/socket-guard environment overrides removed. Private .env contents were not inspected or displayed. Startup enforced Sandbox mode/canonical REST origin, the existing disposable database path and automatic schema creation disabled. The database was preserved; no migration/reset was performed.

Actual catalog request through Vite on 5174 returned checkout_available=true, blocking_reasons=[], return_origin=http://127.0.0.1:5174 and demo-notebook-v1 USD 1.00. This proves local configuration readiness only. Real OAuth/order/approval/capture and separate cancellation remain pending the manual buyer walkthrough; no successful Sandbox payment is claimed by this check.

### Manual approval attempt: seller login blocked

Abhay supplied a screenshot of the actual PayPal Sandbox approval page rejecting login because the signed-in account belongs to the seller for this purchase. This is an observed provider UI error, not a mocked result. Buyer approval and successful capture are not established. No buyer details, credentials or screenshot URL/token are recorded here. Next step: log out of the seller Sandbox session and resume the existing checkout with a distinct Sandbox Personal buyer. Preserve the existing operation/order; do not create a replacement or manually capture based on this error. Separate cancellation verification remains pending.

### Manual approval attempt: currency acceptance blocked

A subsequent user-supplied actual Sandbox screenshot reports that the seller does not accept payments in the buyer's currency. This establishes a provider approval-page blocker, not its precise account-setting cause and not a successful capture. The demo catalog remains fixed at USD 1.00; no currency/price, seller credentials or database changes were made. Next investigation: privately verify the configured Sandbox seller's USD acceptance/account eligibility and buyer/seller test-account regions. Preserve the same operation and reconcile backend status before further action. Successful capture and a deliberate separate cancellation test remain unverified.

### Repeated currency blocker: read-only reconciliation

The latest user-selected Sandbox error URL identifies UNSUPPORTED_PAYEE_CURRENCY. A real read-only backend status lookup for that order returned CREATED, paypal_status CREATED, provider_refreshed true, USD 1.00 and no capture ID. Approval/capture success is not established. No capture POST/new creation was issued by this investigation. Receiving preferences alone have not resolved the observed blocker; seller/buyer country and account type, plus whether the configured app belongs to the seller whose preferences were edited, require private confirmation. No credentials or buyer data were recorded.

### Further currency rejection on a different order

The latest user-supplied approval page again shows UNSUPPORTED_PAYEE_CURRENCY, with a different order identity. Actual read-only reconciliation of that order returned CREATED, provider_refreshed=true, USD 1.00 and no capture ID. No capture or creation was issued by this investigation. The user previously confirmed IN seller and IN buyer; use of the proposed US buyer has not yet been confirmed. Avoid further new orders. If a US buyer was actually used and seller rejection persists, prepare a separate US Sandbox Business/app fixture with matching merchant identity, preserving this database and its historical records. Do not reinterpret the screenshot as proof of a specific account restriction or successful payment.

### Actual Sandbox checkout completed

The user's frontend screenshot shows Sandbox capture verified for creation operation 7d028e23-bda6-4ff7-be68-2d01bb84cdbc. Read-only inspection of the preserved disposable database matched that operation to order 5A238031TF679540C, internal payment 0b595188-40a5-4bd5-aff8-03b7d2d49d9b and provider capture 5WE62397F5803822E: COMPLETED, demo-notebook-v1, USD 1.00 (100 minor units). Audit transitions are PENDING -> CREATED -> APPROVED -> CAPTURING -> COMPLETED, ending with paypal.capture.completed. Actual backend GET status agrees with these identifiers, amount and completed state. No extra capture was sent during verification, and no credentials or buyer details were inspected/recorded.

This is actual Sandbox checkout evidence, distinct from mocked tests. The terminal GET uses the stored backend-verified capture record; no independent fresh provider capture-detail lookup or provider-dashboard comparison was performed in this follow-up. The screenshot alone does not establish which account-country change resolved earlier approval errors. Separate deliberate cancellation verification remains pending, as do the previously listed webhook/authentication/AI limits.

### Cancellation follow-up: no capture verified, callback evidence pending

Abhay reported cancelled returned. Read-only backend/provider reconciliation of the latest ambient order 050039741E2575710 returned CREATED, USD 1.00, provider_refreshed=true and capture_id=null. Its database audit contains only payment.created and paypal.order.created, with no capture-start/completion event. This establishes no recorded capture for this order at inspection time, not provider voiding or a verified cancel callback.

The accessible in-app frontend tab displayed a different older order (6JB89361YP921700D), awaiting approval, rather than the latest cancellation order. The ambient provider tab still referenced a currency error. Therefore the current frontend cancellation callback/order identity could not be correlated and end-to-end cancellation remains partially verified pending the user's returned frontend state/order. No payment mutation, new order, forced timeout or credential inspection occurred.

### Actual cancellation return verified for the correlated order

The user's returned-frontend screenshot supplies the previously missing correlation: operation 1ff24263-7d9d-4b45-878d-1f9d91badc84, order 529629813H303324W, demo-notebook-v1 USD 1.00. The UI explicitly shows Approval cancelled and backend state CREATED, without claiming provider voiding/payment success. Read-only database inspection matches that operation to the same order and internal payment 00823628-f539-446d-a2c5-b2c323cb0af2. Actual backend GET returns CREATED, USD 1.00, capture_id=null, provider_refreshed=true. Audit contains payment.created and paypal.order.created only, with no capture-start/completion event. Thus the observed cancellation return and absence of capture agree for this order at verification time. The prior ambient currency-error order was a different order and is not this cancellation test.

Manual Sandbox success and separate cancellation-return scenarios are now verified at the documented UI/backend-record level. Cancellation does not void the PayPal order or guarantee it can never be approved later. No additional capture/creation, forced timeout, credential read, commit, push, main merge, deployment or submission was performed by this follow-up. Independent provider-dashboard comparison of the successful capture remains unperformed; previous authentication/webhook/AI and broader reliability limits still apply.

### Independent seller Dashboard comparison: partial match

Abhay supplied an actual Sandbox Business seller Activity screenshot. The payment row shows Completed, gross USD 1.00, displayed 31 October 2026 at 4:18 AM, fee USD 0.40 and net USD 0.60. Gross amount/status and displayed clock time agree with the successful backend record (capture-completed audit 2026-10-30 22:48:17 UTC / 2026-10-31 04:18:17 IST). The Dashboard list screenshot does not expose its timezone or transaction/capture ID. Therefore exact identity comparison to capture 5WE62397F5803822E remains pending user confirmation from transaction details; do not mark independent Dashboard verification complete yet. No buyer name, email or screenshot was copied into the repository. The cancelled order 529629813H303324W remains separate. No payment operation or code change was performed.


### Independent seller Dashboard comparison completed

Abhay supplied the Sandbox Business seller transaction-details screenshot confirming transaction/capture ID 5WE62397F5803822E, gross USD 1.00, Checkout type and Completed status. The provider Custom field exactly matches internal payment ID 0b595188-40a5-4bd5-aff8-03b7d2d49d9b. Dashboard transaction time is 31 October 2026 04:18:16 GMT+5:30 (30 October 2026 22:48:16 UTC); backend capture-completed audit is 22:48:17.088598 UTC, approximately one second later. Identity, amount/currency, status and time therefore agree across the user-observed frontend, persisted backend evidence and independently viewed seller Dashboard. Buyer details and the screenshot itself were not copied into the repository.

This closes the independent Dashboard comparison for the successful order 5A238031TF679540C. Cancellation order 529629813H303324W remains a distinct test with verified cancellation UI, CREATED provider-refreshed state and no capture at inspection time. Historical pending statements above describe earlier checkpoints and are superseded by this result.

Integration readiness: ready for review as a local Sandbox checkout milestone, with one actual successful payment and separate cancellation return verified. This is not production readiness or complete hackathon MVP readiness. Authentication/merchant ownership, verified webhooks, automatic ambiguous-creation recovery, cross-device recovery, PostgreSQL/multi-host execution, split captures/refunds/disputes, transaction history/metrics and AI remain absent or unverified as previously documented. Automated results are reused from the saved checkpoint: 193 backend tests, 14 frontend health tests and 31 checkout tests; lint/build/Ruff/dependency checks passed then. No application code changed during this Dashboard comparison; only documentation checks are rerun. No new payment, capture, refund, commit, push, merge, deployment or submission was performed.
