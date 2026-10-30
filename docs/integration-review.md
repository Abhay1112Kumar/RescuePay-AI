# Frontend/backend integration review

Date: 2026-10-31. Scope: combine the pushed feature branches for review without changing payment logic, enabling checkout, contacting PayPal, pushing, or merging into `main`.

## Git sources and preservation

| Source | Pinned commit |
| --- | --- |
| `origin/main` | `fb2be914b8b3b3d619ad07838a28a97b3ab9475b` |
| `origin/feature/frontend` | `9401599b043dca7207715f2564951d97a70a7b42` |
| `origin/feature/backend` | `b9d4b561bdaf55cfb3d606973e7d3cc9fd6cd696` |

The separate `integration/frontend-backend` branch starts at the pinned main commit and merges both feature histories. The original checkout remains on `feature/frontend`; its untracked root instructions, project context and frontend skill are not imported or committed. No stash or deletion is used.

## Integration decisions

- Resolve the root `.gitignore` add/add conflict by retaining both branches' dependency, build, Python, environment/secret, local database, editor and frontend-backup exclusions. Preserve the `.env.example` exceptions.
- Rename backend `Agents.md` through an intermediate filename to canonical `AGENTS.md` for Windows. Retain the complete backend engineering guidance and add shared integration boundaries. There must be only one root instruction filename case variant.
- Preserve `docs/api-contract.md` exactly as supplied by the backend branch. Document discrepancies here rather than silently rewriting Chetan's contract.
- Keep application sources and backend tests/configuration unchanged from their feature branches. Keep checkout disabled. The optional untracked frontend skill is not made a required tracked dependency.
- Add a current project-context source and this review; replace stale frontend README integration claims with links to current evidence.

## Unresolved payment correctness and compatibility findings

All findings below remain **open**. Passing existing tests is not evidence that they are fixed. Source references are local to this combined tree.

| Finding | Evidence and integration consequence |
| --- | --- |
| Caller-selected amount is not an authorized payable amount | [Payment service](../backend/app/services/payment_service.py): `_validate_business_rules` validates currency/maximum, then `create_order` persists the submitted amount. No authoritative payable-record/price comparison exists. Storing caller input does not make it an authorized price. Amount policy is an unresolved product/backend decision. |
| Incomplete order/merchant identity verification | `_verify_order_matches_record` compares the first purchase unit's amount/currency. It does not explicitly verify returned order ID, merchant identity, reference ID or custom ID against the stored record before trusting results. |
| Captured mismatch can still become success | `_apply_capture_result` logs/audits a captured amount mismatch but can still transition to `COMPLETED`. Reported response money comes from the stored record. This needs backend review and targeted tests before displaying paid status. |
| Completion without capture details | `_apply_capture_result` can mark an order `COMPLETED` using only top-level order status when capture detail is absent. Terminal status then skips subsequent provider refresh. The sufficiency of capture evidence remains unresolved. |
| Uncertain capture is described too strongly in the contract | `_resolve_uncertain_capture` releases the lock to `APPROVED` and raises the original error even when the verification lookup also fails. A `504` therefore does not always mean verified not captured. Do not follow the contract's unconditional retry advice; retain an uncertain state and reconcile before any retry. |
| Stuck lock and concurrency recovery | A process failure after persisting `CAPTURING` has no inspected lease/expiry/recovery path. `get_order` skips refresh for that state. Existing conditional-lock/concurrent-capture tests do not establish crash recovery or safety of simultaneous lookup writes and capture transitions. |
| Creation retries can create separate payments | Each frontend create request produces a new payment/create request ID; `reference_id` is indexed but not unique. Stable provider request IDs do not deduplicate separate frontend create attempts. No client idempotency contract exists. |
| Capture HTTP 200 is not success by itself | The service can return `FAILED` for a declined capture body or `APPROVED` for an unknown capture result. The response schema permits the full status enum, beyond the two capture outcomes emphasized in the contract. |
| Status freshness is ambiguous | `get_order` can return local state with HTTP 200 after a provider refresh failure; `paypal_status:null` also occurs for terminal/no-lookup states. It is not proof of fresh provider verification. |
| State-machine edge paths need targeted coverage | [State machine](../backend/app/services/payment_state.py) disallows `CREATED`/`APPROVED` to `CAPTURE_PENDING`, while lookup can feed such a provider result to `_apply_capture_result`. This is a static concern, not a runtime reproduction in this integration task. |
| Webhooks and ownership protection absent | [Webhook router](../backend/app/api/v1/webhooks.py) and [security module](../backend/app/core/security.py) are placeholders. Contract webhook verification behavior is planned, not implemented. Payment routes have no buyer ownership authorization. |
| Sandbox is a configuration default, not enforced | [Settings](../backend/app/core/config.py) accepts Live mode/arbitrary provider base URLs. Both mode and Sandbox URL must be set explicitly; no provider calls are authorized in this task. |
| Local request timeouts conflict | [Vite proxy](../frontend/vite.config.ts) has a six-second timeout; provider requests allow fifteen seconds each, with multiple calls possible. Future payment requests need separate timeout/reconciliation behavior. The five-second frontend health timeout is suitable only for this health scope. |
| Contract health example is stale | Actual health includes configurable `service` (default `RescuePay-AI`) and `version:"0.2.0"`; contract example uses `rescuepay-backend` and omits version. Existing frontend runtime validation follows implementation. |
| Frontend checkout and data endpoints absent | No order adapters, approval-return/cancel handling, or payment status UI are connected. Backend lacks transaction-list/metrics endpoints. Existing UI's statement that payment APIs are placeholders is stale; its disabled/unconnected state remains appropriate. |

The [API contract](api-contract.md) and backend README remain source documents, not proof of production readiness. No finding is closed by combining branches.

## Verification results

Commands below were executed in this worktree on Windows. Backend commands use `backend/.venv/Scripts/python.exe`; npm commands use `npm.cmd` in PowerShell.

| Working directory | Command/check | Actual result |
| --- | --- | --- |
| Repository root | `python -m venv backend/.venv` | Isolated environment created; system Python packages unchanged |
| `backend/` | `.venv/Scripts/python.exe -m pip install -r requirements.txt --disable-pip-version-check` | Declared requirements installed successfully |
| `backend/` | `.venv/Scripts/python.exe -m pip check` | Passed; no broken requirements |
| `frontend/` | `npm.cmd ci --no-audit --no-fund` | Passed; 27 packages installed; lockfile unchanged |
| `backend/` | `.venv/Scripts/python.exe -m pytest -v --tb=short` | Final run: **132 passed**, one Starlette/httpx deprecation warning |
| `backend/` | `.venv/Scripts/python.exe -m ruff check .` | Passed, with cache-write warnings during concurrent lint/format execution |
| `backend/` | `.venv/Scripts/python.exe -m ruff check --no-cache .` | Passed without the cache-write warnings |
| `backend/` | `.venv/Scripts/python.exe -m ruff format --check .` | Passed; 42 files already formatted |
| `frontend/` | `npm.cmd run lint` | Exit 0; one existing `react-hooks(exhaustive-deps)` warning at `src/App.tsx:201` about a ref read in effect cleanup |
| `frontend/` | `npm.cmd run build` | Passed: TypeScript build and Vite production bundle |
| `frontend/` | `npm.cmd run test:health` | **14 passed**, zero failed; expected Node experimental TypeScript-stripping warning |
| Repository root | Local Markdown path/anchor and instruction-case validation | Passed: 25 links/anchors; one canonical root `AGENTS.md`; full original backend guidance retained |
| Repository root | `git check-ignore --no-index -q` against 11 representative paths | Passed: dependency/build/cache/secret/database/backup exclusions and both `.env.example` exceptions |

The first pytest invocation had **130 passed / 2 failed** because this validation process set `APP_ENV=testing` and `APP_NAME=RescuePay-AI` globally, overriding the configuration tests' intended defaults and synthetic dotenv file. Clearing the process-level `APP_NAME`, `APP_ENV`, `DEBUG` and `API_V1_STR` overrides fixed the test invocation; no application or test source was changed. The final run retained explicit Sandbox mode/base URL, blank provider credentials, and disabled automatic database creation outside test fixtures.

Both pytest runs and the local backend process used an untracked validation-only `sitecustomize.py` under ignored `backend/.venv/validation/`, added through `PYTHONPATH`. Its Python audit hook rejects non-loopback DNS resolution and socket connections. Provider HTTP traffic inside the automated tests uses the existing `httpx.MockTransport` fixtures. No actual PayPal calls or real credentials were used.

Environment: Python 3.13.5, Node 22.17.1, npm 10.9.2; FastAPI 0.162.0, Starlette 1.10.0, Pydantic 2.14.2, pydantic-settings 2.16.2, HTTPX 0.28.1, SQLAlchemy 2.1.6, aiosqlite 0.22.1, Alembic 1.20.1, pytest 9.2.0, pytest-asyncio 1.4.1, Ruff 0.17.3. Frontend uses its committed lockfile, including Vite 8.3.5. Backend requirements have lower bounds rather than a lockfile; these results describe this resolved environment, not every supported dependency combination. The Starlette warning was recorded without installing a new HTTP client or changing tests.

### Real local health verification

The integration backend ran on `http://127.0.0.1:8001`; the separate integration frontend ran on `http://127.0.0.1:5174`, with `RESCUEPAY_API_TARGET=http://127.0.0.1:8001`. The original frontend server on port 5173 was preserved.

- Direct `GET http://127.0.0.1:8001/api/v1/health`: HTTP 200 with `{"status":"ok","service":"RescuePay-AI","version":"0.2.0"}`.
- Proxied `GET http://127.0.0.1:5174/api/v1/health`: HTTP 200 with the identical real FastAPI response.
- Imported the actual frontend `checkBackendHealth` adapter through Node's TypeScript stripping, using a fetcher that resolves its relative path against port 5174: returned `status:"connected"` with the same validated response. This used the running backend, not a fixture.
- Browser verified the combined dashboard and Integrations view: `Connected`, service/version `RescuePay-AI / 0.2.0`, and successful manual health recheck. Both `New payment` and `Checkout unavailable` remained disabled; metrics stayed unavailable.
- No real payment endpoint was called. No credentials or actual `.env` file was created/read. No schema migration against a developer database was needed for health; migration tests used their isolated temporary databases.

Only the health interaction was checked in the browser during this task. This does not claim a fresh responsive/accessibility audit, database readiness, provider connectivity, deployed routing, or a verified payment flow.

## Reproduction boundaries

- Install only the declared dependencies into this worktree's `backend/.venv` and `frontend/node_modules`.
- Do not copy or read a real `.env`. Run the health service with blank provider credentials, Sandbox mode/base URL, `DATABASE_AUTO_CREATE=false`, and a loopback bind address.
- Use only `GET /api/v1/health` for local service verification. No order creation, retrieval, capture or webhook request is authorized for this task; backend automated provider traffic must remain mocked.
- Keep the original frontend preview/process untouched. Use a separate frontend port for the integration worktree.
- Do not treat health as database/provider readiness or production routing validation.

For health-only local startup in separate PowerShell terminals:

```powershell
# From backend/, after installing its declared requirements into .venv.
# This worktree has no real .env; do not copy one for health verification.
$env:PAYPAL_MODE = 'sandbox'
$env:PAYPAL_BASE_URL = 'https://api-m.sandbox.paypal.com'
$env:PAYPAL_CLIENT_ID = ''
$env:PAYPAL_CLIENT_SECRET = ''
$env:DATABASE_AUTO_CREATE = 'false'
$env:DATABASE_ECHO = 'false'
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

```powershell
# From frontend/, after npm.cmd ci.
$env:RESCUEPAY_API_TARGET = 'http://127.0.0.1:8001'
node node_modules/vite/bin/vite.js --host=127.0.0.1 --port=5174 --strictPort
```

The current validation processes additionally use the local network guard described above. Recheck health from the Integrations view. Do not use the backend README's payment walkthrough for this milestone.

## Review disposition

Ready to prepare a **draft integration PR for review**, with the existing frontend lint warning, dependency deprecation warning, stale UI wording and all payment findings disclosed. This is not approval to merge, enable checkout or claim production/payment readiness. No PR was opened and nothing was pushed. Payment and contract fixes must be coordinated and independently verified in subsequent focused work.
