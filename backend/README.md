# RescuePay-AI — Backend (Phase 3)

Production-grade, modular FastAPI backend for the RescuePay-AI collaborative fintech and payment integration system.

**Phase 3 status:** PayPal Sandbox OAuth, order creation, status lookup, and capture are implemented with database persistence, an audited payment state machine, and idempotent capture. Webhooks are planned for Phase 4.

---

## 1. Directory Structure

```text
backend/
├── alembic/                    # Database migrations (async env, SQLite + PostgreSQL)
│   ├── env.py
│   └── versions/
├── alembic.ini
├── app/
│   ├── __init__.py             # Package version (single source of truth)
│   ├── main.py                 # FastAPI application factory, lifespan, CORS
│   ├── api/v1/
│   │   ├── router.py           # Aggregated API v1 router
│   │   ├── deps.py             # Dependency providers (DB session, PayPal client, service)
│   │   ├── health.py           # GET /api/v1/health
│   │   ├── payments.py         # POST /orders, GET /orders/{id}, POST /orders/{id}/capture
│   │   └── webhooks.py         # Webhook router placeholder (Phase 4)
│   ├── core/
│   │   ├── config.py           # Typed settings via pydantic-settings
│   │   ├── exceptions.py       # Domain exceptions with HTTP status + error_code
│   │   ├── error_handlers.py   # Standard error envelope for all failures
│   │   └── logging.py          # Key=value structured logging (stdlib only)
│   ├── db/
│   │   ├── base.py             # Declarative base
│   │   └── session.py          # Async engine + session factory
│   ├── integrations/
│   │   └── paypal.py           # Async PayPal REST client (OAuth cache, Orders v2, capture)
│   ├── models/
│   │   └── payment.py          # Payment (trusted record) + PaymentEvent (audit trail)
│   ├── repositories/
│   │   └── payment_repository.py  # Data access incl. atomic capture lock
│   ├── schemas/
│   │   └── payment.py          # Request/response contracts
│   └── services/
│       ├── payment_state.py    # Payment state machine
│       └── payment_service.py  # Create / lookup / capture workflows
├── tests/
│   ├── conftest.py             # Fixtures: temp SQLite DB, FakePayPal (httpx.MockTransport)
│   ├── test_health.py, test_config.py
│   ├── test_paypal_client.py   # OAuth caching, 401 retry, timeouts, error mapping
│   ├── test_payment_state.py   # Transition rules
│   ├── test_payment_service.py # Persistence, validation, capture safety, concurrency
│   ├── test_payments_api.py    # Endpoint contracts and error envelope
│   └── test_migrations.py      # Alembic upgrade/downgrade matches models
├── .env.example
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 2. Quickstart & Setup (Windows PowerShell)

All commands below should be executed from the `backend/` directory:

```powershell
cd c:\Users\hp\RescuePay-AI\backend
```

### Step 1: Verify Python Version
Ensure Python 3.11 or newer is available:
```powershell
python --version
```
Expected output: `Python 3.11.x` (or newer).

### Step 2: Create Virtual Environment
```powershell
python -m venv .venv
```
*(Alternative using uv: `uv venv --python 3.11 .venv`)*

### Step 3: Activate Virtual Environment
```powershell
.\.venv\Scripts\Activate.ps1
```
*(For Command Prompt: `.\.venv\Scripts\activate.bat` | For Linux/macOS: `source .venv/bin/activate`)*

### Step 4: Install Dependencies
```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Step 5: Configure Environment
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Default values in `.env` are configured safely for local development and PayPal Sandbox.

Then fill in `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` from a **Sandbox** app in the
[PayPal Developer Dashboard](https://developer.paypal.com) (Apps & Credentials). Payment
endpoints return `503 PAYPAL_NOT_CONFIGURED` until both are set. Never commit `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `PAYPAL_MODE` | `sandbox` | `sandbox` or `live` |
| `PAYPAL_BASE_URL` | `https://api-m.sandbox.paypal.com` | PayPal REST base URL |
| `PAYPAL_TIMEOUT_SECONDS` | `15` | Per-request timeout to PayPal |
| `PAYPAL_RETURN_URL` | `http://localhost:5173/payment/return` | Buyer redirect after approval |
| `PAYPAL_CANCEL_URL` | `http://localhost:5173/payment/cancel` | Buyer redirect after cancel |
| `PAYMENT_ALLOWED_CURRENCIES` | `USD` | Comma-separated ISO 4217 allowlist |
| `PAYMENT_MAX_AMOUNT` | `10000.00` | Maximum order amount |
| `LOG_LEVEL` | `INFO` | Root log level |
| `DATABASE_URL` | `sqlite+aiosqlite:///<backend>/rescuepay.db` | Async SQLAlchemy URL. Use `postgresql+asyncpg://...` in deployment |
| `DATABASE_ECHO` | `false` | Log SQL statements |
| `DATABASE_AUTO_CREATE` | `false` | Create tables from models at startup (local only) |

### Step 6: Create the database schema
```powershell
python -m alembic upgrade head
```
This creates `rescuepay.db` next to this README (gitignored). Re-run it after pulling new migrations. To generate a migration after changing models:
```powershell
python -m alembic revision --autogenerate -m "describe change"
```

---

## 3. Running the Application

Start the FastAPI local development server with auto-reload:

```powershell
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Once running:
- **Interactive Swagger Docs (OpenAPI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check Endpoint:** [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
- **OpenAPI Schema JSON:** [http://localhost:8000/api/v1/openapi.json](http://localhost:8000/api/v1/openapi.json)

---

## 4. Sandbox Walkthrough (manual)

With the server running, credentials in `.env`, and the schema created:

1. Open http://localhost:8000/docs and call `POST /api/v1/payments/orders` with:
   ```json
   {"reference_id": "RESCUE-1001", "currency": "USD", "amount": "1.00", "description": "Sandbox test"}
   ```
2. Copy the `href` of the link with `rel: approve` and open it in a browser.
3. Log in with the **Personal** (buyer) sandbox account from Testing Tools > Sandbox Accounts and approve.
4. PayPal redirects to `PAYPAL_RETURN_URL?token=<order_id>&PayerID=...`.
5. Call `GET /api/v1/payments/orders/{order_id}`; `status` should now be `APPROVED`.
6. Call `POST /api/v1/payments/orders/{order_id}/capture`; `status` should be `COMPLETED` with a `capture_id`.
   Sandbox funds move from the buyer account to the business account. Calling capture again returns the same result.

Payment flow in one line: **create → buyer approves → capture → `COMPLETED`**. Only `COMPLETED` means paid.

## 5. Running Tests & Quality Checks

Ensure the virtual environment is activated before running tests:

### Run Automated Tests (pytest)
```powershell
python -m pytest -v
```
All PayPal traffic in the suite is mocked with `httpx.MockTransport`; no network access or credentials are needed.

### Run Ruff Code Quality Linting
```powershell
python -m ruff check .
```
To automatically apply safe fixes:
```powershell
python -m ruff check --fix .
```

### Run Ruff Formatting Check
```powershell
python -m ruff format --check .
```
To auto-format code:
```powershell
python -m ruff format .
```

---

## 6. Windows Troubleshooting Tips

1. **PowerShell Script Execution Policy Error:**
   If running `Activate.ps1` gives an execution policy error, enable script execution for the current user:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```

2. **Windows Store Python Alias Interception:**
   If `python` redirects to the Microsoft Store, disable the App Execution Alias:
   - Go to **Windows Settings** > **Apps** > **Advanced app settings** > **App execution aliases**.
   - Toggle **App Installer (python.exe)** and **App Installer (python3.exe)** to **Off**.
   - Ensure `C:\Users\<username>\.local\bin` or your Python directory is listed first in your User `PATH`.

3. **Port 8000 Already in Use:**
   If port 8000 is occupied, run on another port:
   ```powershell
   python -m uvicorn app.main:app --reload --port 8080
   ```
