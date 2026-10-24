# Frontend instructions

These rules apply to `frontend/`. Read the [shared instructions](../AGENTS.md) and [project context](../docs/project-context.md); preserve working frontend code and follow its conventions.

- Use React + TypeScript with strict, readable types; avoid unjustified `any`. Do not claim compiler strict mode is enabled without checking the tsconfig. Respect installed versions, npm scripts, Vite, and Oxlint; do not replace tooling or add dependencies without a concrete need.
- Inspect relevant components and the API contract before editing. Introduce reusable components when useful, avoiding excessive abstraction or unrelated restructuring.
- When integration is introduced, separate API access and runtime response validation from rendering. Treat API data as untrusted: TypeScript annotations alone do not validate JSON. Handle malformed responses and sanitized service errors.
- Use semantic HTML, accessible names/labels, keyboard navigation, visible focus, and responsive layouts. Verify drawer focus/dismissal and narrow-screen overflow where relevant.
- Provide loading, empty, error, cancellation, and uncertain payment states where applicable. Prevent repeated submissions while a request is in flight. A capture timeout needs status reconciliation rather than a blind retry.
- Do not fabricate activity, metrics, backend connectivity, AI results, or payment success. Deliberately introduced mock/demo data must be explicitly labeled; do not add a demo mode unless it serves the request. A static setup checklist is not a connectivity probe, and backend health does not verify PayPal readiness.
- Keep checkout disabled until backend creation, capture, and status verification are implemented and validated. Buyer approval or redirect alone is insufficient: show success only from an explicit backend confirmation of successful capture or a backend-verified payment record. Keep payment development in Sandbox.
- Keep PayPal Client Secret and access tokens on the backend. Never place secrets in `VITE_` variables or client code. The backend determines or validates payable amounts; frontend display values are not authoritative.
- Do not infer product features from existing or historical copy. The confirmed immediate scope is a PayPal Sandbox payment flow; donation, aid, recovery, target audience, and AI capabilities are not established requirements.
- For application changes, run `npm run lint` and `npm run build` from `frontend/`, fix relevant failures, and report actual results. Check affected interactions and responsive/accessibility behavior when applicable. For documentation-only changes, verify links, paths, and instructions without claiming a fresh application check.

Use the repository-local skill at `../.agents/skills/rescuepay-frontend/SKILL.md` for repeatable frontend implementation, review, and backend API integration work. It does not authorize backend modifications or Git publication.
