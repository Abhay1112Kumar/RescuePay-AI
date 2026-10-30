# RescuePay-AI

React/TypeScript frontend and FastAPI backend combined for local integration review.
Checkout remains disabled. Only frontend-to-backend health connectivity is verified in this integration task; payment APIs and PayPal readiness require separate review.

- [Project context](docs/project-context.md)
- [Integration review, verification results and unresolved payment findings](docs/integration-review.md)
- [Frontend setup](frontend/README.md)
- [Backend setup](backend/README.md)
- [API contract](docs/api-contract.md) (retained from the backend branch; see the review for discrepancies)
- [Repository instructions](AGENTS.md)

Do not follow the backend README's payment walkthrough as part of health-only verification. Use Sandbox exclusively; never configure PayPal Live or commit credentials.
