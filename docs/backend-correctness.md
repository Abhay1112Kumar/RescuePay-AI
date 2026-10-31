# Integration and backend correctness milestone

Historical correctness milestone: 2026-10-31. The results and scope below describe the preceding milestone, not the latest checkout state. See [Sandbox checkout implementation and verification](sandbox-checkout.md) for the approved catalog, frontend flow, new checks and remaining real-provider blocker.

Date: 2026-10-31. Owner: Abhay (frontend, backend, integration, testing, submission preparation). Chetan's existing implementation/history is retained. All work in this milestone is uncommitted on `integration/frontend-backend`, based on `1184c78`; main and remote branches remain unchanged.

## Reproduction and findings disposition

The first new regression run against the existing implementation produced **18 failures / 1 pass**. The already implemented pre-capture amount mismatch check was the passing case; findings were not assumed proven merely because they appeared in an inspection. Provider responses are synthetic fixtures throughout.

| Finding | Current disposition and evidence |
| --- | --- |
| Live/arbitrary REST targets accepted | Reproduced; strict Sandbox settings and HTTP boundary validation added. Tests cover Live mode, Live/arbitrary/HTTP/lookalike/path targets, bypassed Settings, injected clients and redirects. |
| Captured amount/currency mismatch could produce success | Reproduced; matching order/unit/capture evidence is required. Mismatch, missing amount/ID, multiple captures, unknown status and non-final capture cannot produce success. |
| Missing order/merchant/reference/custom identity checks | Reproduced; validate them before capture and before applying provider results. Preflight identity failures issue no capture POST. |
| Top-level COMPLETED without capture details | Reproduced; no longer sufficient. Full explicit capture evidence is required. |
| Capture timeout reset to APPROVED | Reproduced; persist CAPTURE_UNCERTAIN before reconciliation. Approved/no-evidence/failed lookup cannot make it capturable. Tests assert no subsequent capture POST even when a caller repeats capture. |
| Stuck CAPTURING recovery absent | Reproduced; expired lock becomes uncertain and reconciles via GET. Tests cover verified recovery, no-evidence recovery, active-lock preservation and a late original owner being prevented from dispatching after recovery. No lease expiry authorizes a new charge. |
| Concurrent stale lookup could reopen state | Targeted overlap test now proves a delayed approval lookup cannot overwrite an in-flight capture lock. ORM optimistic versions discard stale writes; duplicate captures remain serialized in SQLite tests. |
| Creation retries lacked public operation identity | Confirmed missing contract; required UUID header and persisted unique key added. Tests cover replay across sessions, five concurrent same-key callers, payload conflicts and ambiguous creation. No claim of per-invoice uniqueness or automatic creation reconciliation. |
| Duplicate provider capture identity | Unique-ID conflict now rolls back/quarantines the second result; regression preserves the first completed record without assigning success twice. |
| Backend amount authority absent | Reproduced. Added a small injectable authority interface with fail-closed default. Status lookup also cannot bypass authority when establishing success, including legacy re-verification. Fixed USD payables exist only under tests. No business catalog is shipped; proposed test-item catalog awaits approval. |
| Pending capture lookup transition gap | Covered by a regression: CREATED can observe verified pending capture, repeated pending lookup is safe, and no new capture POST occurs. |
| Provider status freshness ambiguous | Added provider_refreshed flag; a local cached status is distinguishable from a valid provider refresh. Capture success still requires its own evidence. |
| Request validator exception context | Sanitized 422 errors to serializable loc/msg/type entries; regression covers custom currency validator failures without raw input/exception context. |
| Webhooks/authentication/metrics and full checkout UI | Still absent/pending, not closed by these tests. |
| Future payment request timeout budget | Still pending; existing 5-second adapter/6-second proxy are only verified for health. Do not reuse them as a proven payment-client policy. |

## Data migration and safety

Migration `0002` adds nullable unique creation_key, stored approval_url and optimistic version to existing payments. Legacy COMPLETED rows were accepted under weaker rules, so migration moves them to CAPTURE_UNCERTAIN and records an audit event for re-verification. It does not fabricate capture evidence or recapture them. Downgrade refuses unresolved uncertainty rather than exposing it to older retry behavior.

Upgrade, schema agreement, idempotent upgrade, empty-database downgrade and a populated legacy-record upgrade/quarantine/downgrade-guard test were executed against temporary SQLite databases. No developer database was migrated or inspected. Before using an existing database, review the migration, preserve a backup, stop old backend processes, and use `python -m alembic upgrade head`; do not run old payment code against the new uncertainty states. An approved payable source and provider reconciliation are required before historical records can be relied on.

## Actual checks in this task

Working directories are backend/ or frontend/ in the integration worktree. Backend commands use its existing isolated .venv. No dependency manifests/lockfiles or system packages were changed.

| Command/check | Result |
| --- | --- |
| Initial `pytest tests/test_payment_correctness.py -q --tb=no` | 18 failed / 1 passed before fixes |
| Final `.venv/Scripts/python.exe -m pytest -q --tb=short` | **181 passed**, one existing Starlette/httpx deprecation warning |
| `.venv/Scripts/python.exe -m ruff check --no-cache .` | Passed |
| `.venv/Scripts/python.exe -m ruff format --check .` | Passed; 45 files formatted |
| `.venv/Scripts/python.exe -m pip check` | Passed |
| `npm.cmd run lint` | Exit 0; existing ref-cleanup hook warning at App.tsx:201 |
| `npm.cmd run build` | Passed |
| `npm.cmd run test:health` | **14 passed**, zero failed; expected Node TypeScript-stripping warning |
| Direct/proxied real health and actual frontend adapter | Passed after restarting the corrected backend: 8001 to 5174, version 0.2.0 |
| Browser | Connected service/version, manual recheck, accurate disabled-checkout wording, both payment buttons disabled |

Intermediate full runs exposed tests expecting the former retry/weak-evidence contract and fixture identity gaps; those expectations/fixtures were updated explicitly, retaining the original test coverage. Existing provider MockTransport fixtures now echo the internal ID/reference from the synthetic create request and supply explicit test merchant identity/capture evidence. They do not patch or fake application responses in a real integration run.

Pytest and the local backend run with a validation-only Python socket audit guard from ignored .venv/validation, rejecting non-loopback DNS/connections. All provider test traffic is mocked. Health is real local FastAPI traffic, not provider traffic. No PayPal API call, actual secret/.env read, commit, push, main merge, deployment or hackathon submission occurred.

## Compatibility changes and residual limits

See the updated [API contract](api-contract.md). Mandatory creation UUID header, provider_refreshed and uncertainty states are explicit frontend compatibility changes. The frontend still sends only health requests and checkout remains disabled. Do not interpret a capture HTTP 200, redirect, APPROVED or CAPTURE_PENDING as paid.

Known captures require exact full-capture evidence. Split capture, refunds/disputes, authenticated merchant ownership, verified webhooks, PostgreSQL/multi-host execution, real provider credentials/connectivity and full checkout remain outside this verification. A persisted per-operation key does not prevent two deliberately different keys from representing separate purchases. Unknown creation cannot be automatically resolved without a safe provider strategy; unknown capture never becomes retryable solely because time elapsed or the provider still says APPROVED.

The next scope and decisions are summarized in [product feasibility](product-feasibility.md). Current test results establish the covered backend behavior, not production readiness or a functioning AI/Sandbox checkout demo.
