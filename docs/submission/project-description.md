# RescuePay-AI — project description

RescuePay-AI helps a small online merchant investigate incomplete, failed, or
uncertain payments. A FastAPI backend owns payable amounts and verifies PayPal
Sandbox order, capture, state, amount, currency, and audit evidence. A React
frontend presents that evidence clearly, including pending, cancelled,
uncertain, and completed states.

The read-only Gemini integration receives only sanitized, backend-approved
evidence. It can select grounded facts and safe next-action suggestions for an
explanation, but it cannot capture, refund, change amounts, refresh provider
state, or declare payment success. PayPal Sandbox is used exclusively; no live
payments are processed. Gemini is disabled by default and requires explicit
private configuration.

The repository includes local setup instructions, tests, and an MIT licence.
The demonstrated build is a local development milestone, not a production
payment service or autonomous payment agent.
