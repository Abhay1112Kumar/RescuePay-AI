# Secure local payment explanation

The stored-evidence endpoint now has two local-only boundaries: the existing development/loopback gate and an explicit bearer token plus local user ID. Clients send `Authorization: Bearer <private local token>` and `X-RescuePay-Local-User: demo-merchant`. The backend reads the token from `LOCAL_EVIDENCE_TOKEN` and the expected user from `LOCAL_EVIDENCE_USER_ID`.

For private development, create a throwaway token in backend `.env` and keep `LOCAL_EVIDENCE_ENABLED=true`, `APP_ENV=development`, and `LOCAL_EVIDENCE_USER_ID=demo-merchant`. The frontend may use matching local-only `VITE_LOCAL_EVIDENCE_TOKEN` and `VITE_LOCAL_EVIDENCE_USER_ID` values for the developer panel. Do not use this mechanism for production identity, commit either value, or place a real credential in a public client build.

The route accepts only records whose backend reference is explicitly in the synthetic/demo namespace (`synthetic...` or `demo-...`). Missing credentials return 401; a valid token with another user ID also returns 401; records outside the namespace are not projected. The response remains sanitized: no buyer data, descriptions, credentials, raw provider payloads, internal IDs or arbitrary audit details are returned. Payment state, amount, uncertainty and provider freshness remain backend facts. Authentication does not authorize capture, refund, amount changes or AI actions.

This is a minimal local ownership boundary, not account management. It has no password lifecycle, session rotation, MFA, revocation service, durable merchant authorization table, CSRF strategy, rate limiting, audit access policy or production deployment controls. Keep the route loopback-only until a real identity and ownership design is implemented.
