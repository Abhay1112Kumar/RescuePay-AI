# RescuePay-AI

Current verification: actual USD 1.00 PayPal Sandbox checkout, a separate cancellation return, and the seller Dashboard comparison are verified against frontend evidence, backend records, audit transitions, and provider transaction details. The Gemini adapter was validated with exactly two synthetic scenarios (one uncertain and one stale); Gemini remains disabled by default, and live browser-to-Gemini verification is still pending. See [checkout evidence](docs/sandbox-checkout.md) and [Gemini implementation](docs/gemini-implementation.md).

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

Abhay currently owns both applications, integration, testing and submission preparation; Chetan's contributions are retained. Current fixes are uncommitted. Checkout defaults to disabled until explicit private Sandbox setup. Use Sandbox exclusively; never configure PayPal Live or expose credentials. The merchant assistant/read-only AI direction is approved; the explanation adapter is read-only and guarded, while no autonomous payment operation is implemented.

- [Read-only payment evidence/explanation foundation](docs/payment-explanation.md)
- [Judge setup guide](docs/judge-setup.md)
- [Submission materials](docs/submission/)

This repository is licensed under the MIT License; see [LICENSE](LICENSE). Third-party packages and isolated spikes retain their own licences. Authentication is a local demonstration boundary, not production identity management. No live payments or autonomous payment operations exist. AG Studio is an optional isolated spike, not a required dependency; its licensing and judge-period access remain unconfirmed.
