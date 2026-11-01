# RescuePay-AI project context

Current work: [read-only evidence/explanation foundation](payment-explanation.md), feature/payment-explanation in a separate worktree from merged main 8ad3266. No provider is configured; no external model/PayPal calls are authorized. The sanitized local endpoint defaults off. Current changes are uncommitted; preserve the existing integration configuration/database.

Current verification: actual USD 1.00 Sandbox checkout and a separate cancellation return are verified against the frontend evidence, backend records and audit transitions. Independent seller PayPal Dashboard comparison of capture identity, internal payment ID, amount/currency, status and timestamp is complete; see the final checkout evidence. Historical setup/blocker notes below describe earlier stages. Authentication, verified webhooks, AI and the other documented limits remain unresolved. See [checkout evidence](sandbox-checkout.md).

Current milestone: backend-priced Sandbox demo checkout, 2026-10-31. Historical integration-only evidence remains in [integration review](integration-review.md); prior correctness fixes/checks are in [backend correctness](backend-correctness.md); latest implementation and checks are in [Sandbox checkout](sandbox-checkout.md).

## Ownership and preserved work

- RescuePay-AI remains a two-person PayPal AI Hackathon project. Abhay currently handles frontend, backend, integration, testing and final submission preparation because Chetan is unavailable. Preserve Chetan's contributions and credit.
- React + TypeScript + Vite frontend; FastAPI backend; PayPal Sandbox exclusively. Never enable Live or use real payments.
- Verified integration worktree was preserved separately; it already contains both feature histories. No new merge was necessary.
- Integration baseline: main `fb2be91`, frontend `9401599`, backend `b9d4b56`. These are inspected local refs, not a new remote-state verification.
- Saved checkpoint: 8022733 on integration/frontend-backend, pushed by explicit authorization. Subsequent Dashboard-verification documentation updates remain uncommitted. Do not commit, push, merge into main, deploy or submit without an explicit instruction.
- Original frontend checkout remains on `feature/frontend`. Its untracked documents and skills are retained; only requested ownership/context instructions are edited there. The relevant frontend skill was deliberately copied into this integration worktree and updated, without staging unrelated files.
- Follow [root instructions](../AGENTS.md), [frontend instructions](../frontend/AGENTS.md) and the included [frontend skill](../.agents/skills/rescuepay-frontend/SKILL.md).

## Confirmed versus proposed scope

The hackathon requires a meaningful PayPal Sandbox integration and an AI component, a runnable build, English materials, an open-source public repository, and a public YouTube demo under three minutes. The [official page](https://paypalaihackathon.devpost.com/) and [rules](https://paypalaihackathon.devpost.com/rules) were checked on 2026-10-31; the page currently lists November 12, 2026, 12:00 PM PST. No submission/deployment has been performed.

Four reference PDFs are reported by Abhay to exist in ChatGPT but are not in the local workspace; they have not been read here. Abhay approved the small-merchant payment investigation assistant, read-only AI explanation role and backend-owned fixed USD demo catalog. AI must not execute payments, change amounts or independently declare success. No AI provider/model or final commercial pricing authority is selected. See [feasibility review](product-feasibility.md); this milestone does not implement an AI endpoint.

## Implemented and verified in this milestone

- Backend now restricts mode and REST origin to canonical Sandbox, including the HTTP-client boundary, and refuses provider redirects.
- Creation/capture require an authoritative backend payable source; the approved DemoCatalog is now the default authority (notebook USD 1.00, sticker pack USD 2.50). Synthetic test payables remain separate. Public creation accepts item_id only; extra monetary fields are rejected. Persisting caller input is not price authorization.
- Creation has a required public UUID `Idempotency-Key`, a unique persisted operation key and stored approval URL. Replays do not create another provider order; unresolved attempts remain blocked.
- Verified order/merchant/reference/custom-ID and full capture evidence are required for success. Missing or mismatched evidence remains uncertain and cannot produce paid status.
- Capture uncertainty is persisted; stale locks become uncertain and use GET reconciliation without another capture POST. Optimistic versions protect state changes from stale concurrent lookups. Migration `0002` adds the needed fields and quarantines legacy success rows for re-verification.
- Current automated checks and runtime results are recorded in [Sandbox checkout](sandbox-checkout.md). Frontend lint now has no warnings; the drawer cleanup captures its DOM element correctly. The complete guarded checkout flow is covered with mocked provider/controller tests.
- A new disposable database was upgraded through 0002, leaving existing developer storage untouched. Real local health/catalog and disabled-payment gate were verified through Vite on 5174 to FastAPI on 8001. No real secrets/.env were read and no PayPal calls were made.

## Remaining blockers and next milestone

Private configuration and actual Sandbox checkout/cancellation verification are complete at the UI/backend-record level; see the correlated identifiers and audit evidence in the checkout report. Independent successful-capture comparison in the seller PayPal Dashboard is complete; see the final checkout evidence. The local runtime remains Sandbox-only; do not publish its unauthenticated routes.

Authentication/ownership and verified webhooks remain absent; development routes must stay local. Transaction history/list, metrics and AI remain absent. Select the AI provider, sanitized audit contract, access policy and open-source license before the later AI/submission milestone. SQLite tests do not establish PostgreSQL or multi-host correctness. See the checkout report for exact commands, API changes and unresolved creation reconciliation limitations.


## Newly available source material

The four October 3 PDFs are now available at the user-provided Downloads paths and were rendered/OCR reviewed (32 pages), with substantive visual checks. See [source review](hackathon-source-review.md) for current rules, prize stacking, AG Studio licensing/compatibility caveats and the distinction between pasted proposals and implemented code. Earlier statements that the PDFs were unavailable describe prior milestones. Gemini is the intended provider in the supplied brief; no implemented adapter was found in current source. No external AI request or payment call was authorized/executed by this source review.


## Gemini adapter and isolated Studio runtime milestone

Final readiness status: exactly two synthetic Gemini scenarios (one uncertain,
one stale) passed strict validation; Gemini is disabled by default and live
browser-to-Gemini verification remains pending. AG Studio is optional and its
licensing/judge-period access are unconfirmed. The local authentication layer
is a demo ownership boundary, not production identity management.

See [implementation results](gemini-implementation.md). Gemini REST adapter is implemented behind explicit default-off configuration; only mocked provider outputs were tested. No external model or PayPal calls were made. Synthetic evidence panel verification and an isolated AG Studio custom-widget runtime spike completed. Studio evaluation warnings are present; no trial key was activated and judging/deployment license access remains unresolved. All work remains uncommitted on feature/payment-explanation.


Offline Gemini diagnosis: the first authorized synthetic attempt returned HTTP 200 but no validated selection; its root cause remains unknown because only a generic failure was retained. Safe staged diagnostics and a documented Part metadata compatibility fix now have mocked regression coverage. No additional model/payment request was made; real AI panel/uncertain/stale validation remains pending and Gemini stays disabled. See [diagnosis and proposed one-request retest](gemini-implementation.md).


Authorized single synthetic Gemini retest succeeded: one additional request on configured gemini-3.1-flash-lite, STOP, strict selection validation passed, synthetic COMPLETED state preserved. Gemini is disabled after cleanup. Model selected supplied fact/action IDs; all display wording remains backend-authored. This verifies real model/backend selection only; browser replay remains separate. See [actual retest evidence](gemini-implementation.md). No payment calls were made.


Offline recorded real Gemini response replay now verified in the actual frontend panel: selected facts/REVIEW_RECORD, unchanged synthetic COMPLETED state, unverified freshness, keyboard reload, loading/error recovery and 320px layout. This is distinct from a live browser-to-provider test, which remains pending. Bounded uncertain/stale runner mode is prepared and mocked-tested, not authorized/executed externally. See [replay results](gemini-implementation.md).
## Secure local explanation boundary

The evidence/explanation route now requires loopback development mode plus a configured local bearer token and matching demo user header. Only synthetic/demo reference namespaces are projected; missing or mismatched identity is rejected and payment state remains authoritative. This is a local demonstration boundary, not production authentication or durable merchant ownership. Gemini remains disabled and no provider calls were made for this milestone.
The controlled uncertain/stale Gemini retest is complete: exactly two synthetic-only requests on `gemini-3.1-flash-lite` passed strict validation through the secured local auth boundary. Uncertainty, stale freshness and payment states were preserved; no PayPal call or provider refresh occurred. Gemini is disabled after cleanup. This verifies adapter/backend behavior only; live frontend-to-provider verification remains pending.
