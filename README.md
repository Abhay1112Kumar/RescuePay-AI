# RescuePay-AI

Current verification: actual USD 1.00 Sandbox checkout and a separate cancellation return are verified against the frontend evidence, backend records and audit transitions. Independent seller PayPal Dashboard comparison of capture identity, internal payment ID, amount/currency, status and timestamp is complete; see the final checkout evidence. Historical setup/blocker notes below describe earlier stages. Authentication, verified webhooks, AI and the other documented limits remain unresolved. See [checkout evidence](docs/sandbox-checkout.md).

React/TypeScript frontend and FastAPI backend combined for local integration review.
Backend-priced Sandbox demo checkout is implemented with strict identity, idempotency and uncertainty handling. Mocked flows and local API configuration gates are verified; real Sandbox checkout is pending private credentials.

- [Sandbox checkout implementation, checks and private configuration](docs/sandbox-checkout.md)
- [Project context](docs/project-context.md)
- [Integration review, verification results and unresolved payment findings](docs/integration-review.md)
- [Current backend correctness fixes and regression evidence](docs/backend-correctness.md)
- [Approved MVP feasibility and remaining decisions](docs/product-feasibility.md)
- [Frontend setup](frontend/README.md)
- [Backend setup](backend/README.md)
- [API contract](docs/api-contract.md) (updated to the item-only creation contract)
- [Repository instructions](AGENTS.md)

Abhay currently owns both applications, integration, testing and submission preparation; Chetan's contributions are retained. Current fixes are uncommitted. Checkout defaults to disabled until explicit private Sandbox setup. Use Sandbox exclusively; never configure PayPal Live or expose credentials. The merchant assistant/read-only AI direction is approved; no AI endpoint is implemented; no commit, push, deployment or submission is authorized.

- [Read-only payment evidence/explanation foundation](docs/payment-explanation.md) (local-only, default-off, no configured AI provider)
