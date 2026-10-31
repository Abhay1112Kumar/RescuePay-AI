# Approved MVP feasibility review

Current verification: actual USD 1.00 Sandbox checkout and a separate cancellation return are verified against the frontend evidence, backend records and audit transitions. Independent seller PayPal Dashboard comparison of capture identity, internal payment ID, amount/currency, status and timestamp is complete; see the final checkout evidence. Historical setup/blocker notes below describe earlier stages. Authentication, verified webhooks, AI and the other documented limits remain unresolved. See [checkout evidence](sandbox-checkout.md).

Status: MVP direction and backend-priced Sandbox demo catalog approved by Abhay, 2026-10-31. The catalog and guarded checkout are implemented; real provider verification is pending private configuration. AI remains a later milestone and no AI endpoint is implemented. See [checkout evidence](sandbox-checkout.md). The reference PDFs are not in this workspace and have not been read; Abhay supplied the project context, and current official web pages were checked separately.

## Confirmed hackathon constraints

The [official overview](https://paypalaihackathon.devpost.com/) currently lists November 12, 2026, 12:00 PM PST (November 13, 01:30 IST). It requires meaningful PayPal Sandbox and AI use plus a working build. A public open-source repository with setup instructions and a public YouTube video under three minutes are required; hosted deployment is optional when judges can run the build. The [official rules](https://paypalaihackathon.devpost.com/rules) require English materials or translations and five equally weighted criteria: technology, design, impact, innovation and presentation. Checked 2026-10-31. Sponsor-prize qualification is outside this review; verify applicable requirements before targeting an award.

## Feasibility

A small-merchant assistant explaining incomplete/failed payments is technically feasible as a narrow read-only AI experience. The first demo is more achievable with one fixed-price USD Sandbox item, one full capture, one merchant and explicit backend action rules. The merchant audience and read-only AI role are now confirmed. The fixed USD catalog is explicitly a demo fixture; final commercial pricing remains undefined.

The backend should supply verified facts and allowed actions; AI explains those facts, distinguishes uncertainty, and cannot mark paid, change amounts, capture/refund autonomously or override rules. A dashboard alone does not satisfy the AI requirement. Safety also does not establish merchant demand; the impact story needs a concrete audience/problem claim Abhay can substantiate.

## Minimum end-to-end demo

1. Select a clearly labeled backend-owned fixed test item. Resolve USD price server-side; retain one operation key across request/redirect recovery.
2. Create a real Sandbox order, approve with a Sandbox buyer, return to the frontend and capture/status-check through the backend. Show completed only from verified capture details. Represent cancel/pending/error/uncertain states explicitly.
3. Display a sanitized record and verified audit timeline. Generate an AI explanation separating provider facts, stale/cached information and unresolved outcomes; show backend-approved next actions with manual confirmation where relevant.
4. Use actual Sandbox records for the integration segment. Demonstrate uncommon failures separately as clearly labeled synthetic scenarios; never present mocked failures as PayPal responses.
5. Record an English demo under three minutes and provide complete local setup. Deployment is optional; upload/submission is not authorized now.

## API implementation and remaining work

| Area | Proposed minimal contract |
| --- | --- |
| Test catalog | Implemented GET /api/v1/sandbox/catalog: approved fixed demo IDs/USD prices, local readiness and callback origin |
| Creation | Item-ID body with required Idempotency-Key; resolve price/currency server-side instead of accepting authoritative client amounts |
| Recovery | Retain operation/order identity across redirects; define lookup by operation key for creation outcomes with no known order ID, without unsafe creation replay |
| Status/audit | Authenticated sanitized detail/audit projection with refresh provenance; omit raw provider bodies, unnecessary buyer data, tokens and credentials |
| AI | Authenticated read-only explanation endpoint over the sanitized projection, selected model/provider, validated output, failure handling and factuality tests |
| Actions | Backend-calculated allowed actions; explicit user intent for supported capture, never an action inferred from uncertainty |

Current code implements item-only creation, the demo catalog, persistent operation keys, provider_refreshed and uncertainty-preserving capture/status. The frontend retains the same operation key across creation retries and binds return/cancel to the saved order. Sanitized audit/AI APIs and authentication remain future work. See the API contract and checkout evidence for exact current behavior.

## Unresolved decisions and blockers

- Merchant investigation audience, read-only AI role and isolated USD demo catalog are approved. Final commercial pricing authority remains undefined.
- Select AI provider/model, allowed sanitized inputs/outputs, cost/access and retention policy. Never supply secrets in chat.
- Privately configure Sandbox client ID, secret and expected merchant ID when real checkout verification begins; use a Sandbox buyer account. These are unnecessary for the completed mocked milestone.
- Choose access/ownership protection suitable for the demo. Current unauthenticated development routes must not be exposed publicly.
- Choose an open-source license and confirm asset rights before publication. No license is currently selected/added; preserve Chetan's credit.
- Review sponsor-specific requirements only if pursuing those prizes. The four PDFs remain unavailable locally and may contain additional details.

Finish actual Sandbox verification after private configuration, then plan the read-only AI milestone once model, access and sanitized input contracts are selected. Do not invent autonomous money movement or infer requirements from the project name.
