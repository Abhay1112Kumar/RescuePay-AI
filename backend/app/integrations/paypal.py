"""Async PayPal REST API client.

Responsibilities:
- OAuth 2.0 client-credentials token acquisition with in-memory caching.
- Orders API v2 calls (create, retrieve) with idempotent request identifiers.
- Translation of transport failures and PayPal error payloads into domain
  exceptions that carry no credentials or raw provider bodies.

The client never logs the Authorization header, the client secret, or the
access token.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import (
    OrderNotFoundError,
    PayPalAPIError,
    PayPalAuthError,
    PayPalNotConfiguredError,
    PayPalTimeoutError,
)

logger = logging.getLogger(__name__)

OAUTH_TOKEN_PATH = "/v1/oauth2/token"
ORDERS_PATH = "/v2/checkout/orders"

# Refresh the token this many seconds before PayPal says it expires.
TOKEN_REFRESH_MARGIN_SECONDS = 60


class PayPalClient:
    """Client for communicating with the PayPal REST API (Sandbox and Live)."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._owns_http_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=settings.PAYPAL_BASE_URL,
            timeout=httpx.Timeout(settings.PAYPAL_TIMEOUT_SECONDS),
        )
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this instance created it."""
        if self._owns_http_client:
            await self._http.aclose()

    # ------------------------------------------------------------------ #
    # OAuth
    # ------------------------------------------------------------------ #
    def _token_is_valid(self) -> bool:
        return self._access_token is not None and self._clock() < self._token_expires_at

    def invalidate_token(self) -> None:
        """Drop the cached token so the next call fetches a fresh one."""
        self._access_token = None
        self._token_expires_at = 0.0

    async def get_access_token(self) -> str:
        """Return a cached access token, fetching a new one when missing or expiring."""
        if not self._settings.paypal_configured:
            raise PayPalNotConfiguredError()

        if self._token_is_valid():
            return self._access_token  # type: ignore[return-value]

        async with self._token_lock:
            # Another coroutine may have refreshed while we waited for the lock.
            if self._token_is_valid():
                return self._access_token  # type: ignore[return-value]
            return await self._fetch_access_token()

    async def _fetch_access_token(self) -> str:
        logger.info("paypal.oauth.token.requested")
        try:
            response = await self._http.post(
                OAUTH_TOKEN_PATH,
                data={"grant_type": "client_credentials"},
                auth=(
                    self._settings.PAYPAL_CLIENT_ID,
                    self._settings.PAYPAL_CLIENT_SECRET,
                ),
                headers={"Accept": "application/json"},
            )
        except httpx.TimeoutException as exc:
            logger.warning("paypal.oauth.token.timeout")
            raise PayPalTimeoutError() from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "paypal.oauth.token.transport_error",
                extra={"error": type(exc).__name__},
            )
            raise PayPalAPIError("Payment provider is unreachable.") from exc

        body = _safe_json(response)
        if response.status_code != 200:
            logger.error(
                "paypal.oauth.token.failed",
                extra={
                    "paypal_status": response.status_code,
                    "paypal_error": body.get("error"),
                },
            )
            raise PayPalAuthError()

        token = body.get("access_token")
        expires_in = body.get("expires_in")
        if not isinstance(token, str) or not isinstance(expires_in, int | float):
            logger.error("paypal.oauth.token.malformed_response")
            raise PayPalAuthError(
                "Payment provider returned a malformed token response."
            )

        self._access_token = token
        self._token_expires_at = (
            self._clock() + float(expires_in) - TOKEN_REFRESH_MARGIN_SECONDS
        )
        logger.info("paypal.oauth.token.acquired", extra={"expires_in": expires_in})
        return token

    # ------------------------------------------------------------------ #
    # Generic authenticated request
    # ------------------------------------------------------------------ #
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        _retry_on_401: bool = True,
    ) -> tuple[int, dict[str, Any]]:
        """Send an authenticated request and return ``(status_code, json_body)``.

        A 401 invalidates the cached token and the request is retried exactly once.
        Transport errors and timeouts raise domain exceptions.
        """
        token = await self.get_access_token()
        request_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if headers:
            request_headers.update(headers)

        try:
            response = await self._http.request(
                method, path, json=json, headers=request_headers
            )
        except httpx.TimeoutException as exc:
            logger.warning(
                "paypal.request.timeout", extra={"method": method, "path": path}
            )
            raise PayPalTimeoutError() from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "paypal.request.transport_error",
                extra={"method": method, "path": path, "error": type(exc).__name__},
            )
            raise PayPalAPIError("Payment provider is unreachable.") from exc

        if response.status_code == 401 and _retry_on_401:
            logger.info("paypal.request.unauthorized_retry", extra={"path": path})
            self.invalidate_token()
            return await self._request(
                method, path, json=json, headers=headers, _retry_on_401=False
            )

        body = _safe_json(response)
        logger.info(
            "paypal.request.completed",
            extra={
                "method": method,
                "path": path,
                "paypal_status": response.status_code,
                "paypal_debug_id": body.get("debug_id"),
            },
        )
        return response.status_code, body

    # ------------------------------------------------------------------ #
    # Orders API v2
    # ------------------------------------------------------------------ #
    async def create_order(
        self, payload: dict[str, Any], request_id: str
    ) -> dict[str, Any]:
        """Create a checkout order.

        ``request_id`` is sent as ``PayPal-Request-Id``; PayPal treats repeated
        requests with the same id as the same order instead of creating duplicates.
        """
        status, body = await self._request(
            "POST",
            ORDERS_PATH,
            json=payload,
            headers={"PayPal-Request-Id": request_id},
        )
        if status in (200, 201):
            return body
        _raise_for_error(status, body)

    async def get_order(self, order_id: str) -> dict[str, Any]:
        """Retrieve an order by its PayPal id."""
        status, body = await self._request("GET", f"{ORDERS_PATH}/{order_id}")
        if status == 200:
            return body
        if status == 404:
            raise OrderNotFoundError(debug_id=body.get("debug_id"))
        _raise_for_error(status, body)

    async def capture_order(self, order_id: str, request_id: str) -> dict[str, Any]:
        """Capture an approved order.

        ``request_id`` must be stable per payment: PayPal de-duplicates captures
        that share a ``PayPal-Request-Id``, so a retry after an uncertain outcome
        cannot charge the buyer twice.
        """
        status, body = await self._request(
            "POST",
            f"{ORDERS_PATH}/{order_id}/capture",
            json={},
            headers={
                "PayPal-Request-Id": request_id,
                "Prefer": "return=representation",
            },
        )
        if status in (200, 201):
            return body
        if status == 404:
            raise OrderNotFoundError(debug_id=body.get("debug_id"))
        _raise_for_error(status, body)


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    """Parse a JSON body, returning an empty dict for empty or non-JSON responses."""
    if not response.content:
        return {}
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _first_issue(body: dict[str, Any]) -> str | None:
    """Extract ``details[0].issue`` from a PayPal error body, if present."""
    details = body.get("details")
    if isinstance(details, list) and details and isinstance(details[0], dict):
        issue = details[0].get("issue")
        if isinstance(issue, str):
            return issue
    return None


def _raise_for_error(status: int, body: dict[str, Any]) -> None:
    """Translate a non-success PayPal response into a domain exception."""
    name = body.get("name")
    debug_id = body.get("debug_id")
    paypal_name = name if isinstance(name, str) else None
    issue = _first_issue(body)
    if status == 401:
        raise PayPalAuthError(debug_id=debug_id)
    if 400 <= status < 500:
        # Client-side problem with our request (e.g. INVALID_REQUEST, UNPROCESSABLE_ENTITY).
        raise PayPalAPIError(
            "The payment provider rejected the request.",
            debug_id=debug_id,
            paypal_status=status,
            paypal_name=paypal_name,
            issue=issue,
        )
    raise PayPalAPIError(
        debug_id=debug_id,
        paypal_status=status,
        paypal_name=paypal_name,
        issue=issue,
    )
