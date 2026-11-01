# RescuePay-AI judge setup

This guide runs the local, PayPal Sandbox-only demonstration. It does not
authorize live payments, production deployment, or autonomous payment actions.
Never select PayPal Live and never place secrets in Git, frontend variables,
screenshots, logs, or chat.

## Prerequisites (Windows)

- Git, Python 3.11+ and Node.js/npm compatible with the checked-in lockfiles.
- A disposable local database directory; do not use a production database.
- A PayPal Sandbox Business seller and separate Sandbox Personal buyer, created
  privately in the PayPal Developer Dashboard.
- Gemini access is optional for the demo. The application defaults to disabled.

## Install

From the repository root in PowerShell:

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Set-Location frontend
npm ci
npm run build
Set-Location ..
```

## Disposable database and private configuration

Create a new disposable database path and apply migrations using the backend's
documented Alembic command. Do not point this run at a shared or production
database. Copy `backend/.env.example` to a private, ignored `backend/.env` and
fill values from the Sandbox app and seller account privately:

- PayPal client ID and client secret: Sandbox **Apps & Credentials**.
- Seller merchant ID: Sandbox Business account profile/business information.
- `SANDBOX_CHECKOUT_ENABLED=true` only for a private Sandbox walkthrough.
- Loopback return and cancel URLs must match the frontend origin and paths.
- `GEMINI_ENABLED=false` for the default reproducible run.
- If Gemini is explicitly enabled for an authorized synthetic test, configure
  `GEMINI_API_KEY` and the documented model/deadline values privately; never
  commit or display them.
- Configure the local demo bearer token and demo user identity as documented in
  the backend configuration example. These are development guards, not accounts.

Configuration readiness does not prove PayPal connectivity. Keep credentials
server-side and use a distinct Sandbox buyer; never use real payment details.

## Start the applications

Terminal 1 (repository root, activated backend environment):

```powershell
Set-Location backend
..\backend\.venv\Scripts\python.exe -m alembic upgrade head
..\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Terminal 2:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Open `http://127.0.0.1:5174/checkout`. Use the configured local bearer token
and matching local-user header only in private browser/dev tooling. Do not put
either value in a public URL or screenshot.

## Checkout walkthrough

1. Confirm the page reports local configuration readiness; health alone does
   not enable checkout.
2. Select the backend-priced USD 1.00 demo notebook and create one order.
3. Follow the validated HTTPS Sandbox approval URL and sign in as the separate
   Sandbox Personal buyer.
4. Approve once and return to the exact loopback return URL.
5. The frontend requests backend status/capture verification. Only an explicit
   backend-confirmed capture may display completed. A redirect, token, or HTTP
   200 alone is never success.

## Cancellation walkthrough

Create a separate demo order, follow its Sandbox approval URL, cancel, and
return to the cancel path. The UI must show cancellation/pending state without
claiming provider VOIDED or success. Preserve the order for read-only status
reconciliation; do not blindly capture or create a replacement.

## Explanation-panel walkthrough

Use only an authorized synthetic/demo reference. The panel shows sanitized
backend facts, payment state, amount/currency, uncertainty, freshness, and
backend-approved safe-action codes. Gemini is disabled by default, so the
verified facts remain usable while the panel states that AI is unavailable.
If an explicitly authorized synthetic Gemini run is performed, model-selected
IDs remain grounded in supplied evidence; Gemini cannot capture, refund, alter
amounts, or declare success.

## Limitations

The demo is local and Sandbox-only. Synthetic evidence is not a live payment
record. Local authentication is a development ownership boundary, not
production identity management. Webhooks, durable multi-host recovery,
production account management, public hosting, and live browser-to-Gemini
verification remain outside this readiness milestone. AG Studio stays an
optional isolated spike because licence and judge-period access are unconfirmed.
