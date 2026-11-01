# Two-minute-thirty-second demo script

**0:00–0:15 — Problem.** Explain that merchants need a safe explanation of
incomplete or uncertain payments without unsafe retries.

**0:15–0:35 — Backend-priced checkout.** Select the USD 1.00 demo notebook and
show that the backend, not the browser, supplies the amount and currency.

**0:35–0:55 — Sandbox approval.** Approve once with a separate Sandbox Personal
buyer and return to the local merchant page.

**0:55–1:15 — Verified result.** Show the backend-confirmed completed state,
matching order/capture evidence, and audit transitions. State that a redirect
or HTTP 200 is not treated as success.

**1:15–1:30 — Cancellation.** Show a separate cancelled approval returning to
the cancel path without claiming provider VOIDED or payment success.

**1:30–1:55 — Evidence explanation.** Show sanitized facts, uncertainty,
freshness, local ownership checks, and backend-approved safe actions.

**1:55–2:15 — Gemini boundary.** Explain that Gemini can select grounded facts
and suggestions only. Payment state and all payment operations remain backend
authoritative; Gemini is disabled by default.

**2:15–2:30 — Safety and limits.** State Sandbox-only operation, local setup,
synthetic-data limitations, missing production identity/webhooks, and that AG
Studio is optional pending licensing/judge-access confirmation.
