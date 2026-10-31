# RescuePay-AI backend

Current verification: actual USD 1.00 Sandbox checkout and a separate cancellation return are verified against the frontend evidence, backend records and audit transitions. Independent comparison of the successful capture in PayPal Dashboard remains pending. Historical setup/blocker notes below describe earlier stages. Authentication, verified webhooks, AI and the other documented limits remain unresolved. See [checkout evidence](../docs/sandbox-checkout.md).

FastAPI backend originally contributed by Chetan and currently maintained by Abhay. This milestone hardens the Phase 3 foundation; it does not establish production readiness or a verified provider checkout.

PayPal Sandbox exclusively. Live/arbitrary REST origins are rejected at configuration and HTTP boundaries. Checkout defaults to disabled and requires explicit private Sandbox setup. The catalog and frontend flow are implemented; real provider verification is pending. See [context](../docs/project-context.md), [correctness evidence](../docs/backend-correctness.md), and [API contract](../docs/api-contract.md).

## Local setup

Run from backend/. Python 3.11+ is required (current verification: 3.13.5).

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Health needs no credentials, real .env or database migration:

```powershell
$env:PAYPAL_MODE = 'sandbox'
$env:PAYPAL_BASE_URL = 'https://api-m.sandbox.paypal.com'
$env:PAYPAL_CLIENT_ID = ''
$env:PAYPAL_CLIENT_SECRET = ''
$env:PAYPAL_MERCHANT_ID = ''
$env:DATABASE_AUTO_CREATE = 'false'
$env:DATABASE_ECHO = 'false'
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Health: http://127.0.0.1:8001/api/v1/health; OpenAPI docs: http://127.0.0.1:8001/docs. Health does not check database/credentials/PayPal connectivity. For the separate integration preview, set RESCUEPAY_API_TARGET to this backend origin before starting Vite on port 5174.

## Payment configuration and gate

The default PayableSource is the clearly labeled backend-owned DemoCatalog: demo-notebook-v1 = USD 1.00 and demo-stickers-v1 = USD 2.50. Public creation accepts item_id only, never client prices. Separate synthetic authorities remain test-only. This is not final commercial pricing.

Follow [private Sandbox setup and verification](../docs/sandbox-checkout.md) for the complete local walkthrough. The catalog endpoint performs local configuration/schema checks without contacting PayPal. Health never enables checkout.

| Setting | Requirement/default |
| --- | --- |
| SANDBOX_CHECKOUT_ENABLED | false by default; explicit local opt-in required |
| PAYPAL_MODE | sandbox only |
| PAYPAL_BASE_URL | https://api-m.sandbox.paypal.com only |
| PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET | Private backend-only Sandbox configuration; never share in chat or use VITE_ variables |
| PAYPAL_MERCHANT_ID | Expected Sandbox merchant identity for payment validation |
| PAYPAL_TIMEOUT_SECONDS | 15 per request; positive, at most 60 |
| PAYMENT_CAPTURE_LEASE_SECONDS | 120; expiry allows reconciliation, never another charge |
| PAYPAL_RETURN_URL / PAYPAL_CANCEL_URL | Exact same-origin loopback handlers; .env.example uses 127.0.0.1:5174/payment/return and /payment/cancel (Settings defaults still localhost:5173) |
| PAYMENT_ALLOWED_CURRENCIES / PAYMENT_MAX_AMOUNT | USD / 10000.00; limits are not a price authority |
| DATABASE_URL | Local SQLite via aiosqlite by default |
| DATABASE_ECHO / DATABASE_AUTO_CREATE | false / false |

When real Sandbox verification starts, the maintainer may copy .env.example and configure privately. Do not copy/read a real .env for health checks. No real credentials were needed/read in this milestone.

## Persistence and migrations

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
```

Review/back up existing storage and stop old backend processes before migration. Migration 0002 adds creation keys, stored approval links and optimistic versions; legacy COMPLETED rows become CAPTURE_UNCERTAIN with an audit event because prior verification was weaker. Temporary-database tests cover this behavior. No developer database was migrated. Downgrade refuses unresolved uncertainty instead of exposing it to old retry behavior. Do not use automatic table creation to upgrade existing storage.

SQLite is the verified test database. PostgreSQL/multi-host behavior is unverified; no PostgreSQL driver is included in current requirements.

## Checks

```powershell
.venv/Scripts/python.exe -m pytest -q --tb=short
.venv/Scripts/python.exe -m ruff check --no-cache .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m pip check
```

Provider calls are mocked. Avoid developer credential/application overrides when running configuration tests; fixtures install synthetic settings. Current verification also used an ignored socket guard for non-loopback network isolation. See the correctness report for actual results and warnings.

## Payment behavior

Creation requires UUID Idempotency-Key. Replays return the persisted operation; conflicting bodies return 409. Ambiguous creation remains blocked instead of creating a second order. This is per-operation idempotency, not per-invoice uniqueness.

Capture uses conditional state/version checks and verifies provider identity/full capture evidence. Unknown outcomes stay CAPTURE_UNCERTAIN and reconcile via GET. Expired locks never authorize another capture. Approval, redirect, pending, top-level order COMPLETED and HTTP 200 are insufficient for paid status.

Authentication/ownership and webhook handlers remain placeholders. Refunds, public deployment and AI are not implemented. The buyer checkout flow is implemented and mocked; actual Sandbox approval/capture remains pending private configuration. See the checkout report for current evidence.
