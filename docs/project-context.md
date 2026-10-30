# RescuePay-AI project context

Integration snapshot: 2026-10-31. This file describes the combined integration branch; the original frontend checkout's untracked context and skills are preserved separately and were not imported.

## Sources and scope

- Base: `origin/main` at `fb2be914b8b3b3d619ad07838a28a97b3ab9475b`.
- Frontend: `origin/feature/frontend` at `9401599b043dca7207715f2564951d97a70a7b42`.
- Backend: `origin/feature/backend` at `b9d4b561bdaf55cfb3d606973e7d3cc9fd6cd696`.
- Integration branch: `integration/frontend-backend`, in a separate worktree. No push or merge into `main` is authorized.
- Abhay primarily owns frontend; Chetan primarily owns backend. Business audience, payable-record/amount policy, donation/aid requirements and AI behavior remain unconfirmed.
- Follow the [root instructions](../AGENTS.md) and [frontend instructions](../frontend/AGENTS.md). See the [integration review](integration-review.md) for actual check outcomes, reproducible commands and unresolved findings.

## Implemented versus verified

- Frontend: responsive dashboard, honest empty/unavailable metrics, disabled payment actions, runtime-validated health adapter, shared health state, manual recheck and Vite `/api` proxy. No payment requests or return/cancel flow are implemented.
- Backend: FastAPI root/health, order creation, order status lookup and capture routes; OAuth client; SQLAlchemy payment/event persistence; Alembic migration; payment state machine; conditional capture lock and stable per-payment capture request ID.
- Webhook handling/signature verification, authentication/ownership authorization and transaction-list/metrics endpoints remain absent/placeholders.
- Backend health returns `status`, configurable `service`, and version `0.2.0`. It checks no external service or database and cannot enable checkout.
- Payment correctness findings from the prior backend inspection remain unresolved. Existing tests, even when passing, do not establish those findings fixed or establish provider readiness. No payment logic is changed by integration.
- This task permits local health verification only, with no real credentials and no PayPal calls. See current results in the review; do not treat older inspection results as fresh execution evidence.

## Configuration and next milestone

Use Python 3.11+ and the declared backend requirements in an isolated environment. Health-only startup needs no PayPal credentials or migrated payment tables. Keep `PAYPAL_MODE=sandbox`, the Sandbox REST base URL, blank provider credentials and `DATABASE_AUTO_CREATE=false` for this task. Never read real `.env` files or place secrets in `VITE_` settings.

The frontend uses relative `/api` requests. Set the non-secret `RESCUEPAY_API_TARGET` before Vite startup to select the local backend origin. CORS is DEBUG-only for localhost/127.0.0.1 ports 3000/5173; the same-origin local proxy avoids depending on it. Deployment routing remains a separate task.

The smallest complete integration milestone is real local health connectivity through the existing adapter/proxy while checkout remains disabled. Payment integration requires coordinated resolution and verification of the [open findings](integration-review.md#unresolved-payment-correctness-and-compatibility-findings), then separately authorized Sandbox testing. Health success is not payment success.
