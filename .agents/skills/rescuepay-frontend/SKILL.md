---
name: rescuepay-frontend
description: Implement, review, or integrate backend APIs for the RescuePay-AI React and TypeScript frontend. Use for its dashboard, checkout, payment-status UI, accessibility, and responsive behavior; not unrelated frontend projects or backend-only work.
---

# RescuePay frontend workflow

Deliver the smallest complete requested frontend milestone, preserving existing work and verifying the actual result. Abhay currently owns both applications, integration, testing and hackathon preparation. The user's current authorization permits necessary backend correctness fixes; this frontend skill does not narrow that authorization. Never use PayPal Live. Git commits/publication, deployment and submission require explicit instructions.

## Inspect and establish scope

1. Read applicable [root instructions](../../../AGENTS.md), [frontend instructions](../../../frontend/AGENTS.md), and [project context](../../../docs/project-context.md). Inspect status/current branch, relevant components, styles, installed tooling, and existing changes before proposing edits.
2. Inspect the API contract at `../../../docs/api-contract.md` relative to this skill directory when present. That file may be absent on the frontend branch: use read-only `git show origin/feature/backend:docs/api-contract.md` if the ref exists. The context document links the inspected contract snapshot. Do not recreate schemas in this skill or copy the backend into the frontend branch.
3. Establish backend readiness from relevant handlers, schemas, services and provider integration, not documentation examples. Use read-only `git show` / `git ls-tree` for backend-only files; do not switch branches or fetch unless needed. Record the inspected ref and separate source inspection from runtime verification. Explain discrepancies without silently rewriting the contract.
4. State a focused plan in simple Hinglish: requested outcome, files to change, integration dependencies, and relevant checks. Keep code and documentation in English. Record unresolved business/AI scope without inventing features or blocking independent foundation work.

## Implement or review the milestone

- Follow the existing React + TypeScript, npm, Vite and Oxlint setup. Keep types readable and reusable components proportionate; separate API access and runtime response validation from rendering when adding integration. Avoid unjustified dependencies, `any`, and unrelated refactors.
- Preserve working UI. Distinguish backend health from PayPal/payment readiness. Never infer connectivity from static status text or fabricate transactions, metrics, AI output, or payment results. Label deliberately requested demo/mock behavior explicitly.
- Use semantic HTML, accessible labels, visible focus, keyboard navigation and responsive layouts. Check drawer dismissal/focus and narrow-screen overflow when affected.
- Handle applicable loading, empty, malformed-response, error, cancellation, pending and uncertain states. Prevent repeated submissions while a request is in flight. Keep checkout disabled while required backend functionality is absent or unverified.

## Payment invariants

- Stay in PayPal Sandbox. Keep PayPal Client Secret and access tokens on the backend; never read `.env` secrets or place secrets in `VITE_` variables/client code.
- The backend determines or validates payable amounts. Frontend display values and user-supplied amounts do not establish an authorized charge.
- Buyer approval or a browser redirect alone is not proof of payment. Show success only from a backend response explicitly confirming successful capture, or a backend-verified payment record.
- Treat capture timeouts as uncertain outcomes. Do not blindly retry capture; reconcile with backend status before deciding the next action.
- Do not claim idempotency, webhook authenticity verification, persistence, or reconciliation exists unless inspected and verified. Account for duplicate callbacks and concurrent submissions without inventing backend guarantees.

## Verify and report

1. For application changes, run `npm run lint` and `npm run build` from `frontend/`; fix relevant failures. Run appropriate existing tests and inspect affected UI behavior when useful. Do not install a test framework just to mirror implementation details.
2. For documentation-only work, validate local links/relative paths, filename case and skill frontmatter; do not claim a fresh application check.
3. Summarize changes, commands actually run and their results, backend dependencies, unresolved contract differences, and remaining limitations. Distinguish implemented UI from verified integration, and identify the next small milestone. Do not commit, push, merge or switch branches without an explicit request.
