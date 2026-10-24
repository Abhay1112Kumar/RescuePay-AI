# RescuePay-AI — Backend (Phase 1)

Production-grade, modular FastAPI backend foundation for the RescuePay-AI collaborative fintech and payment integration system.

---

## 1. Directory Structure

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application factory and entry point
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py       # Aggregated API v1 router
│   │       ├── health.py       # Health check endpoint (/api/v1/health)
│   │       ├── payments.py     # Payment router placeholder (Phase 2+)
│   │       └── webhooks.py     # Webhook router placeholder (Phase 2+)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # Typed settings via pydantic-settings
│   │   └── security.py         # Security utilities placeholder
│   ├── db/
│   │   └── __init__.py         # Database session placeholder
│   ├── integrations/
│   │   ├── __init__.py
│   │   └── paypal.py           # PayPal REST API client placeholder
│   ├── models/
│   │   └── __init__.py         # Data models placeholder
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── health.py           # Pydantic schema for HealthResponse
│   │   └── payment.py          # Payment schemas placeholder
│   └── services/
│       ├── __init__.py
│       └── payment_service.py  # Business logic service placeholder
├── tests/
│   ├── __init__.py
│   ├── test_health.py          # Health check endpoint unit & integration tests
│   └── test_config.py          # Settings, env overrides, and isolation tests
├── .env.example                # Example environment variables template
├── requirements.txt            # Project dependencies
├── pyproject.toml              # Build metadata, Ruff rules, and pytest config
└── README.md                   # Backend documentation
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

## 4. Running Tests & Quality Checks

Ensure the virtual environment is activated before running tests:

### Run Automated Tests (pytest)
```powershell
python -m pytest -v
```

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

## 5. Windows Troubleshooting Tips

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
