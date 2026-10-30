# RescuePay-AI — API Contract

This document outlines the API design, schemas, and endpoint specifications for communication between the Frontend (React) and Backend (FastAPI).

## Base Configuration

- **Base URL:** `/api/v1`
- **Content-Type:** `application/json`
- **Default Port:** `8000` (Backend) / `5173` or `3000` (Frontend)

---

## Standard Response Conventions

### Success Response Envelope
Where applicable, responses return structured JSON with appropriate HTTP status codes:
- `200 OK`: Request succeeded.
- `201 Created`: Resource successfully created.
- `204 No Content`: Successful operation with no response body.

### Standard Error Response Format
All errors follow a consistent structure:
```json
{
  "detail": "Description of the error",
  "error_code": "RESOURCE_NOT_FOUND",
  "timestamp": "2026-10-24T12:00:00Z"
}
```
- `detail` is a string, except for `422` where it is FastAPI's list of field errors.
- `paypal_debug_id` is added when PayPal supplied one; quote it when contacting PayPal support.

Common status codes:
- `400 Bad Request`: Business validation failure (see each endpoint).
- `401 Unauthorized`: Missing or invalid authentication token.
- `403 Forbidden`: Insufficient permissions.
- `404 Not Found`: Requested resource does not exist.
- `422 Unprocessable Entity`: Pydantic request schema validation error.
- `500 Internal Server Error`: Server exception (sanitized in production).
- `502 Bad Gateway`: PayPal returned an error or was unreachable.
- `503 Service Unavailable`: PayPal credentials are not configured on the backend.
- `504 Gateway Timeout`: PayPal did not respond in time.

Error codes currently emitted:

| `error_code` | Status | Meaning |
|---|---|---|
| `REQUEST_VALIDATION_ERROR` | 422 | Request body or path failed schema validation |
| `PAYMENT_VALIDATION_FAILED` | 400 | Currency not allowed or amount over limit |
| `ORDER_NOT_FOUND` | 404 | PayPal has no order with that id |
| `RESOURCE_NOT_FOUND` | 404 | Unknown route |
| `PAYPAL_NOT_CONFIGURED` | 503 | Backend has no PayPal credentials |
| `PAYPAL_AUTH_FAILED` | 502 | PayPal rejected the backend's credentials |
| `PAYPAL_API_ERROR` | 502 | PayPal returned an error or was unreachable |
| `PAYPAL_TIMEOUT` | 504 | PayPal call exceeded the timeout |
| `INTERNAL_ERROR` | 500 | Unhandled server error |

---

## Endpoints

### 1. Health Check

#### `GET /api/v1/health`
Checks whether the backend service is running.

- **Request:** None
- **Response (200 OK):**
```json
{
  "status": "ok",
  "service": "rescuepay-backend"
}
```

---

### 2. Payments

**Status:** `POST /payments/orders` and `GET /payments/orders/{order_id}` are implemented (Phase 2). Capture is planned for Phase 3.

Payment endpoints return `503 PAYPAL_NOT_CONFIGURED` when the backend has no PayPal credentials, so the frontend can show a "payments unavailable" state instead of a generic failure.

#### `POST /api/v1/payments/orders`
Creates a PayPal checkout order and returns the approval link the buyer must visit.

- **Security Note:** The backend validates the amount against its own limits (allowed currencies, maximum amount). Phase 3 will derive the amount from a backend-owned record instead of accepting it from the client. Nothing is charged at this step; funds move only on capture.
- **Request Body:**
```json
{
  "reference_id": "RESCUE-1001",
  "currency": "USD",
  "amount": "25.00",
  "description": "Emergency donation / aid payment"
}
```
- **Validation rules (422 on failure):**
  - `reference_id`: 1 to 64 characters, letters, digits, `_` or `-`, must start with a letter or digit.
  - `currency`: exactly three letters (case-insensitive, normalized to upper case).
  - `amount`: number or numeric string, greater than 0, at most two decimal places, at most 10 digits. Send it as a string to avoid float rounding.
  - `description`: optional, at most 127 characters.
- **Business rules (400 `PAYMENT_VALIDATION_FAILED` on failure):**
  - Currency must be in the backend allowlist (default: `USD`).
  - Amount must not exceed the backend maximum (default: `10000.00`).
- **Response (201 Created):**
```json
{
  "order_id": "5O190127TN364715T",
  "status": "CREATED",
  "request_id": "0d0c7a2e-3f52-4b6f-9d8e-3a1c6c0f5e21",
  "links": [
    { "href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/5O190127TN364715T", "rel": "self", "method": "GET" },
    { "href": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T", "rel": "approve", "method": "GET" },
    { "href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/5O190127TN364715T/capture", "rel": "capture", "method": "POST" }
  ]
}
```
  - Redirect the buyer to the link whose `rel` is `approve` (PayPal may return `payer-action` instead; treat both the same).
  - `request_id` is the idempotency key the backend sent to PayPal. The frontend does not need to use it, but it is useful when reporting a problem.
  - After approval PayPal redirects the buyer to `PAYPAL_RETURN_URL` with `token=<order_id>` in the query string. The frontend must then call the capture endpoint (Phase 3); a redirect alone does not mean the payment succeeded.

#### `GET /api/v1/payments/orders/{order_id}`
Retrieves the current order status from PayPal.

- **Path Parameters:**
  - `order_id` (string): 10 to 32 alphanumeric characters. Other values return 422.
- **Response (200 OK):**
```json
{
  "order_id": "5O190127TN364715T",
  "status": "APPROVED",
  "created_at": "2026-10-24T12:00:00Z",
  "amount": { "currency_code": "USD", "value": "25.00" }
}
```
  - `status` is PayPal's order status: `CREATED`, `SAVED`, `APPROVED`, `PAYER_ACTION_REQUIRED`, `VOIDED`, or `COMPLETED`. Only `COMPLETED` means funds were captured.
  - `created_at` and `amount` may be `null` if PayPal omits them.
- **Errors:** `404 ORDER_NOT_FOUND` for an unknown order.

#### `POST /api/v1/payments/orders/{order_id}/capture` (planned, Phase 3)
Captures funds for an approved PayPal order.

- **Path Parameters:**
  - `order_id` (string): The PayPal order ID returned during creation.
- **Request Body:** `{}`
- **Response (200 OK):**
```json
{
  "order_id": "5O190127TN364715T",
  "capture_id": "1JS80234KJ293810L",
  "status": "COMPLETED",
  "amount": {
    "currency_code": "USD",
    "value": "25.00"
  }
}
```

---

### 3. Webhooks

#### `POST /api/v1/webhooks/paypal`
Receives asynchronous event notifications from PayPal (e.g., `PAYMENT.CAPTURE.COMPLETED`).

- **Verification:** Headers (`PAYPAL-AUTH-ALGO`, `PAYPAL-CERT-URL`, `PAYPAL-TRANSMISSION-ID`, `PAYPAL-TRANSMISSION-SIG`, `PAYPAL-TRANSMISSION-TIME`) are verified against PayPal Sandbox before processing.
- **Response (200 OK):**
```json
{
  "status": "received"
}
```

---

## Payment Safety and Idempotency Rules

1. **Backend Verification:** The client must never dictate the authorized captured amount without backend validation.
2. **Idempotency:** Payment captures must be idempotent to prevent duplicate debits.
3. **Capture Confirmation:** A transaction is considered paid only upon explicit confirmation from PayPal capture or verified webhook event.
