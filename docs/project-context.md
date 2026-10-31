# RescuePay-AI project context

Current verification: actual USD 1.00 Sandbox checkout and a separate cancellation return are verified against the frontend evidence, backend records and audit transitions. Independent seller PayPal Dashboard comparison of capture identity, internal payment ID, amount/currency, status and timestamp is complete; see the final checkout evidence. Historical setup/blocker notes below describe earlier stages. Authentication, verified webhooks, AI and the other documented limits remain unresolved. See [checkout evidence](sandbox-checkout.md).

Current milestone: backend-priced Sandbox demo checkout, 2026-10-31. Historical integration-only evidence remains in [integration review](integration-review.md); prior correctness fixes/checks are in [backend correctness](backend-correctness.md); latest implementation and checks are in [Sandbox checkout](sandbox-checkout.md).

## Ownership and preserved work

- RescuePay-AI remains a two-person PayPal AI Hackathon project. Abhay currently handles frontend, backend, integration, testing and final submission preparation because Chetan is unavailable. Preserve Chetan's contributions and credit.
- React + TypeScript + Vite frontend; FastAPI backend; PayPal Sandbox exclusively. Never enable Live or use real payments.
- Verified worktree: `F:/ab/Abhay1112Kumar/RescuePay-AI-integration`, branch `integration/frontend-backend`, HEAD `1184c78` before this task. It already contains both feature histories; no new merge was necessary.
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
