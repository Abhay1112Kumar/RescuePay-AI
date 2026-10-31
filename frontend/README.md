# RescuePay AI frontend

Current verification: actual USD 1.00 Sandbox checkout and a separate cancellation return are verified against the frontend evidence, backend records and audit transitions. Independent seller PayPal Dashboard comparison of capture identity, internal payment ID, amount/currency, status and timestamp is complete; see the final checkout evidence. Historical setup/blocker notes below describe earlier stages. Authentication, verified webhooks, AI and the other documented limits remain unresolved. See [checkout evidence](../docs/sandbox-checkout.md).

A responsive React + TypeScript dashboard built with Vite. Includes overview, transaction history, and integration readiness views, with responsive navigation, transaction search/status filters, and accessible empty states.

## Local development

```sh
npm ci
npm run dev
```

Run commands from `frontend/`. Validate with `npm run lint` and `npm run build`; use `npm run preview` to serve the production build locally.

## Backend health and local API routing

The UI checks `GET /api/v1/health` on mount and exposes a manual **Recheck backend health** button in Integrations. The sidebar and workspace notice share the same checking/connected/unavailable state. There is no automatic polling; navigating between dashboard views does not start another check. Recheck is disabled while a request is in flight, and unmounting cancels the request.

The adapter in `src/api/health.ts` validates JSON at runtime: `status` must be `ok`, and `service` and `version` must be nonempty strings. Service names are configurable by the backend. HTTP failures, network errors, invalid responses (including HTML fallback pages), and a five-second timeout covering the response body are handled without displaying raw server errors. No credentials are sent by this health request.

The response is compatible with integrated backend commit `b9d4b56`, specifically `backend/app/api/v1/health.py` and `backend/app/schemas/health.py` (version `0.2.0`). The current API contract includes version; historical inspection discrepancies remain recorded in the integration review. See [project context](../docs/project-context.md) and the [integration review](../docs/integration-review.md) for current evidence and discrepancies.

Vite proxies local `/api` requests to `http://127.0.0.1:8000` by default. To target another locally running backend, set a non-secret shell variable **before starting Vite**:

```powershell
$env:RESCUEPAY_API_TARGET = 'http://127.0.0.1:8080'
npm run dev
```

`RESCUEPAY_API_TARGET` is read by Vite's Node-side configuration, not bundled into the browser; use an HTTP(S) backend origin without credentials. Changing it requires restarting Vite. Do not put PayPal secrets or access tokens in this setting, `VITE_` variables, or client code.

This proxy is a **local development arrangement** that lets the browser use a same-origin `/api` path without changing backend CORS. The installed Vite preview server also inherits this proxy configuration; a production build does not provide API routing. A deployed frontend/backend requires its own `/api` reverse proxy or separately agreed API-origin/CORS configuration.

If no local backend is running, an unavailable result means reachability was not confirmed; it is not proof of a broken backend. A successful health check only confirms a valid response from the configured health endpoint. It does not verify PayPal credentials, Sandbox connectivity, payment APIs, or checkout readiness.

## Health adapter checks

```sh
npm run test:health
```

The tests use Node's built-in test runner and TypeScript stripping (verified on Node 22.17.1; its experimental warning is expected). No test dependencies are added. Response fixtures cover validation, errors, timeouts, cancellation, and an isolated HTTP fixture verifies routing through the actual Vite configuration. Fixture success is not live backend or PayPal verification; fixtures are never loaded into the application.

## Backend-priced Sandbox checkout

Open /checkout. Follow [private setup and verification](../docs/sandbox-checkout.md) and the [API contract](../docs/api-contract.md). The backend serves two explicitly labeled fixed USD demo items; the browser submits only item_id plus a UUID Idempotency-Key. Health cannot enable payment actions. The catalog readiness response, exact return origin and usable session storage gate creation/approval/capture.

The flow covers selection, creation, same-tab Sandbox approval, /payment/return and /payment/cancel, capture and verified status. Both applications validate the exact HTTPS www.sandbox.paypal.com/checkoutnow destination and bound order token. Session storage retains one operation under rescuepay.sandbox.checkout.v1: create retries keep the same key; identity is saved before redirect and capture-attempt intent before capture. Only an explicit new-checkout action replaces the operation. Do not close the tab, clear storage or reset the database while an outcome is unresolved; lost local identity requires manual reconciliation, not another payment.

Return parameters never prove payment. Capture requires fresh backend APPROVED evidence and no previous capture attempt. A timeout, reload or duplicate callback leads to read-only status reconciliation, never blind capture retry. COMPLETED requires an explicit backend-verified capture with matching identity/money; HTTP 200, APPROVED, redirect and CAPTURE_PENDING are not paid. Cancellation expresses browser intent and does not void the provider order. Pending, failed, loading, cancelled and uncertain states are explicit.

Health keeps its five-second deadline and six-second proxy. Payment mutations allow 120 seconds, status 45 seconds and catalog eight seconds; Vite's payment proxy permits 150 seconds. A client timeout still leaves a potentially completed server operation. All failures are sanitized and response JSON is validated at runtime.

```sh
npm run lint
npm run build
npm run test:health
npm run test:checkout
```

Checkout tests use Node's built-in runner and TypeScript stripping, without added dependencies. They test the actual adapter/controller with synthetic HTTP/storage/navigation fixtures. They do not prove real PayPal connectivity. Current health/catalog/configuration-gate checks use actual local FastAPI through Vite; actual Sandbox OAuth, buyer approval and capture await private configuration.

Metrics remain unavailable and transaction history remains empty because list/metrics APIs are absent. Current checkout status appears in Checkout, not a fabricated history row. Authentication, verified webhooks and AI are not implemented; these development routes must remain local. No provider credentials belong in VITE_ configuration or frontend code.
