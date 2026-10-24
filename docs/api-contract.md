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

Common status codes:
- `400 Bad Request`: Validation failure or malformed payload.
- `401 Unauthorized`: Missing or invalid authentication token.
- `403 Forbidden`: Insufficient permissions.
- `404 Not Found`: Requested resource does not exist.
- `422 Unprocessable Entity`: Pydantic request schema validation error.
- `500 Internal Server Error`: Server exception (sanitized in production).

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

#### `POST /api/v1/payments/orders`
Initiates a payment order and requests PayPal order approval details.

- **Security Note:** Payable amount is calculated or verified by the backend — never blindly trusted from client input.
- **Request Body (planned):**
```json
{
  "reference_id": "RESCUE-1001",
  "currency": "USD",
  "amount": "25.00",
  "description": "Emergency donation / aid payment"
}
```
- **Response (201 Created):**
```json
{
  "order_id": "5O190127TN364715T",
  "status": "CREATED",
  "links": [
    {
      "href": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T",
      "rel": "approve",
      "method": "GET"
    }
  ]
}
```

#### `POST /api/v1/payments/orders/{order_id}/capture`
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

#### `GET /api/v1/payments/orders/{order_id}`
Retrieves current transaction status directly from PayPal / internal transaction record.

- **Path Parameters:**
  - `order_id` (string)
- **Response (200 OK):**
```json
{
  "order_id": "5O190127TN364715T",
  "status": "COMPLETED",
  "created_at": "2026-10-24T12:00:00Z"
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
