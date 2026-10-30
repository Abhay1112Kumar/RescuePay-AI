# RescuePay AI frontend

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

The response is compatible with integrated backend commit `b9d4b56`, specifically `backend/app/api/v1/health.py` and `backend/app/schemas/health.py` (version `0.2.0`). The retained API contract example omits `version` and uses a different default service name; that example is not accepted as a complete health response. See [project context](../docs/project-context.md) and the [integration review](../docs/integration-review.md) for current evidence and discrepancies.

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

## Payment integration state

- Backend order creation, lookup and capture routes are implemented in the combined branch, with unresolved correctness findings. This frontend makes no payment or transaction requests. Webhooks and authentication remain placeholders.
- Metrics display “Unavailable” / “No data yet”; they do not imply a zero balance or successful payments.
- Transaction history is empty. Search and status filters operate on this empty state; there are no seeded transactions.
- New payment and checkout controls are disabled. No payment creation, recovery, or success is simulated.
- The integration checklist describes payment readiness; the separate backend health panel checks reachability only. “Frontend ready” only refers to the UI.
- Navigation, filters, and the reporting period are local React state and reset on reload.

Before enabling checkout, resolve the [payment correctness findings](../docs/integration-review.md#unresolved-payment-correctness-and-compatibility-findings), connect the required frontend flows and data sources, and separately authorize and verify the complete Sandbox flow. Existing tests and health success do not establish payment readiness. Secrets belong on the backend, never in client code.
