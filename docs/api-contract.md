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
| `ORDER_NOT_APPROVED` | 409 | Capture attempted before buyer approval |
| `PAYMENT_INSTRUMENT_DECLINED` | 409 | PayPal declined the buyer's funding source |
| `CAPTURE_IN_PROGRESS` | 409 | A concurrent capture holds the lock |
| `AMOUNT_MISMATCH` | 409 | PayPal order amount/currency differ from backend record |
| `PAYMENT_INVALID_STATE` | 409 | Payment is in a terminal state |
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

**Status:** order creation, status lookup, and capture are implemented (Phase 3). Webhooks are planned for Phase 4.

Payment endpoints return `503 PAYPAL_NOT_CONFIGURED` when the backend has no PayPal credentials, so the frontend can show a "payments unavailable" state instead of a generic failure.

#### Payment status values

The backend keeps its own record of every payment. `status` in responses is the **backend** status, not PayPal's:

| `status` | Meaning | Frontend action |
|---|---|---|
| `CREATED` | PayPal order exists; buyer has not approved | Send buyer to the approve link |
| `APPROVED` | Buyer approved at PayPal | Call capture |
| `CAPTURING` | A capture is in flight | Wait, then poll status |
| `CAPTURE_PENDING` | PayPal accepted the capture; funds not yet settled (e.g. e-check) | Show "processing"; poll status later |
| `COMPLETED` | Funds captured. **The only success state.** | Show success |
| `FAILED` | Unrecoverable (provider rejection, amount mismatch) | Show failure; start a new order |
| `VOIDED` | Order cancelled or expired at PayPal | Start a new order |

`PENDING` exists internally before the PayPal order is created and is never returned.

#### `POST /api/v1/payments/orders`
Records the payment in the backend database, creates a PayPal checkout order, and returns the approval link.

- **Security Note:** The backend stores the amount and currency before contacting PayPal. That stored record, not the request, is what capture later verifies against. Nothing is charged at this step.
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
  "payment_id": "0d0c7a2e-3f52-4b6f-9d8e-3a1c6c0f5e21",
  "status": "CREATED",
  "request_id": "9b1f3c2e-7d4a-4e8b-a1c2-5f6e7d8c9b0a",
  "links": [
    { "href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/5O190127TN364715T", "rel": "self", "method": "GET" },
    { "href": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T", "rel": "approve", "method": "GET" },
    { "href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/5O190127TN364715T/capture", "rel": "capture", "method": "POST" }
  ]
}
```
  - `order_id` is the PayPal order id. Use it for the status and capture endpoints.
  - `payment_id` is the backend's internal id, useful for support and reconciliation.
  - Redirect the buyer to the link whose `rel` is `approve` (PayPal may return `payer-action` instead; treat both the same).
  - After approval PayPal redirects the buyer to `PAYPAL_RETURN_URL?token=<order_id>&PayerID=...`. The frontend must then call the capture endpoint. A redirect alone does not mean the payment succeeded.

#### `GET /api/v1/payments/orders/{order_id}`
Returns the backend payment record. While the payment is still in progress the backend refreshes it from PayPal first, so an approval or cancellation that happened on PayPal's side is reflected.

- **Path Parameters:**
  - `order_id` (string): 10 to 32 alphanumeric characters. Other values return 422.
- **Response (200 OK):**
```json
{
  "order_id": "5O190127TN364715T",
  "payment_id": "0d0c7a2e-3f52-4b6f-9d8e-3a1c6c0f5e21",
  "reference_id": "RESCUE-1001",
  "status": "APPROVED",
  "paypal_status": "APPROVED",
  "amount": { "currency_code": "USD", "value": "25.00" },
  "capture_id": null,
  "created_at": "2026-10-30T12:00:00Z",
  "updated_at": "2026-10-30T12:03:10Z"
}
```
  - `paypal_status` is PayPal's raw order status from the latest lookup, or `null` when no lookup was made (payment already terminal) or PayPal was unreachable.
  - `capture_id` is set once a capture has been accepted by PayPal.
- **Errors:** `404 ORDER_NOT_FOUND` when the backend has no record of the order.

#### `POST /api/v1/payments/orders/{order_id}/capture`
Captures funds for an order the buyer has approved. Call it when the buyer lands on the return URL.

- **Path Parameters:**
  - `order_id` (string): The PayPal order id returned during creation.
- **Request Body:** none (an empty `{}` is also accepted).
- **Safety:** before capturing, the backend re-reads the order from PayPal and checks that its amount and currency equal the stored record. It uses a stable idempotency key per payment, so a retry after a timeout cannot charge twice. Calling capture again on a captured payment returns the same result.
- **Response (200 OK):**
```json
{
  "order_id": "5O190127TN364715T",
  "payment_id": "0d0c7a2e-3f52-4b6f-9d8e-3a1c6c0f5e21",
  "capture_id": "1JS80234KJ293810L",
  "status": "COMPLETED",
  "amount": { "currency_code": "USD", "value": "25.00" }
}
```
  - `status` is `COMPLETED` when funds were captured, or `CAPTURE_PENDING` when PayPal is still settling. Treat only `COMPLETED` as paid.
- **Errors (409 Conflict unless noted):**

| `error_code` | Meaning | Frontend action |
|---|---|---|
| `ORDER_NOT_APPROVED` | Buyer has not approved yet | Send buyer back to the approve link |
| `PAYMENT_INSTRUMENT_DECLINED` | Buyer's funding source was declined | Send buyer back to the approve link to pick another method |
| `CAPTURE_IN_PROGRESS` | Another capture call is running | Wait a moment, then poll status |
| `AMOUNT_MISMATCH` | PayPal's order amount differs from the backend record; payment marked `FAILED` | Show failure; start a new order |
| `PAYMENT_INVALID_STATE` | Payment is `FAILED` or `VOIDED` | Start a new order |
| `ORDER_NOT_FOUND` (404) | Unknown order | Start a new order |
| `PAYPAL_TIMEOUT` (504) | PayPal did not answer; outcome was verified as not captured | Retry capture |

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

1. **Backend record is the authority.** The amount and currency are stored before the PayPal order is created. Capture compares PayPal's order against that record and refuses on any difference.
2. **Capture is idempotent.** Each payment has one stable idempotency key for capture; PayPal de-duplicates retries that carry it. A repeated capture call on a captured payment returns the stored result without contacting PayPal.
3. **One capture at a time.** A database-level lock (`CAPTURING`) stops concurrent capture requests, including from multiple backend processes.
4. **Uncertain outcomes are verified, not retried blindly.** On a timeout or PayPal 5xx the backend re-reads the order; if PayPal shows it completed, the payment is marked `COMPLETED`, otherwise the lock is released and the client may retry.
5. **Paid means `COMPLETED`.** A redirect to the return URL, an `APPROVED` status, or a `CAPTURE_PENDING` status is not payment confirmation.
6. **Full audit trail.** Every state change is written to `payment_events` together with the state change itself.
