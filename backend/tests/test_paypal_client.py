"""Tests for the PayPal REST client: OAuth caching, retries, and error mapping."""

import asyncio
import logging

import httpx
import pytest

from app.core.exceptions import (
    OrderNotFoundError,
    PayPalAPIError,
    PayPalAuthError,
    PayPalNotConfiguredError,
    PayPalTimeoutError,
)
from app.integrations.paypal import OAUTH_TOKEN_PATH, ORDERS_PATH, PayPalClient
from tests.conftest import (
    SAMPLE_ORDER_ID,
    TEST_ACCESS_TOKEN,
    TEST_CLIENT_ID,
    TEST_CLIENT_SECRET,
    FakePayPal,
    created_order_response,
    make_paypal_client,
    make_settings,
    order_detail_response,
    token_response,
)


async def test_token_fetched_once_and_cached(
    paypal_client: PayPalClient, fake_paypal: FakePayPal
) -> None:
    t1 = await paypal_client.get_access_token()
    t2 = await paypal_client.get_access_token()
    assert t1 == t2 == TEST_ACCESS_TOKEN
    assert fake_paypal.token_calls == 1


async def test_token_request_uses_basic_auth_and_client_credentials(
    paypal_client: PayPalClient, fake_paypal: FakePayPal
) -> None:
    await paypal_client.get_access_token()
    request = fake_paypal.requests_to("POST", OAUTH_TOKEN_PATH)[0]
    expected_auth = httpx.BasicAuth(TEST_CLIENT_ID, TEST_CLIENT_SECRET)._auth_header
    assert request.headers["Authorization"] == expected_auth
    assert request.content.decode() == "grant_type=client_credentials"


async def test_token_refreshed_after_expiry(settings, fake_paypal: FakePayPal) -> None:
    now = {"t": 1000.0}
    client = make_paypal_client(settings, fake_paypal, clock=lambda: now["t"])
    fake_paypal.set("POST", OAUTH_TOKEN_PATH, lambda: token_response(expires_in=300))

    await client.get_access_token()
    now["t"] += 100  # still valid (300 - 60 margin = 240s window)
    await client.get_access_token()
    assert fake_paypal.token_calls == 1

    now["t"] += 200  # past the refresh margin
    await client.get_access_token()
    assert fake_paypal.token_calls == 2


async def test_concurrent_callers_share_single_token_fetch(settings) -> None:
    fake = FakePayPal()

    async def slow_token(request: httpx.Request) -> httpx.Response:
        fake.requests.append(request)
        if request.url.path == OAUTH_TOKEN_PATH:
            fake.token_calls += 1
            await asyncio.sleep(0.02)
            return token_response()
        return httpx.Response(404)

    http = httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL, transport=httpx.MockTransport(slow_token)
    )
    client = PayPalClient(settings, http_client=http)

    tokens = await asyncio.gather(*(client.get_access_token() for _ in range(5)))
    assert set(tokens) == {TEST_ACCESS_TOKEN}
    assert fake.token_calls == 1


async def test_missing_credentials_raise_not_configured(
    fake_paypal: FakePayPal,
) -> None:
    settings = make_settings(PAYPAL_CLIENT_ID="", PAYPAL_CLIENT_SECRET="")
    client = make_paypal_client(settings, fake_paypal)
    with pytest.raises(PayPalNotConfiguredError):
        await client.get_access_token()
    assert fake_paypal.token_calls == 0


async def test_invalid_credentials_raise_auth_error(
    paypal_client: PayPalClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST",
        OAUTH_TOKEN_PATH,
        httpx.Response(
            401,
            json={
                "error": "invalid_client",
                "error_description": "Client Authentication failed",
            },
        ),
    )
    with pytest.raises(PayPalAuthError):
        await paypal_client.get_access_token()


async def test_malformed_token_response_raises_auth_error(
    paypal_client: PayPalClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST", OAUTH_TOKEN_PATH, httpx.Response(200, json={"unexpected": True})
    )
    with pytest.raises(PayPalAuthError):
        await paypal_client.get_access_token()


async def test_create_order_sends_bearer_and_request_id(
    paypal_client: PayPalClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.Response(201, json=created_order_response())
    )
    data = await paypal_client.create_order({"intent": "CAPTURE"}, request_id="req-123")
    assert data["id"] == SAMPLE_ORDER_ID

    request = fake_paypal.requests_to("POST", ORDERS_PATH)[0]
    assert request.headers["Authorization"] == f"Bearer {TEST_ACCESS_TOKEN}"
    assert request.headers["PayPal-Request-Id"] == "req-123"
    assert request.headers["Content-Type"] == "application/json"
    assert fake_paypal.body_of(request) == {"intent": "CAPTURE"}


async def test_401_invalidates_token_and_retries_once(settings) -> None:
    fake = FakePayPal()
    order_attempts = {"n": 0}

    def orders():
        order_attempts["n"] += 1
        if order_attempts["n"] == 1:
            return httpx.Response(401, json={"name": "INVALID_TOKEN"})
        return httpx.Response(201, json=created_order_response())

    fake.set("POST", ORDERS_PATH, orders)
    client = make_paypal_client(settings, fake)

    data = await client.create_order({}, request_id="r")
    assert data["id"] == SAMPLE_ORDER_ID
    assert order_attempts["n"] == 2
    assert fake.token_calls == 2  # initial + refresh after 401


async def test_persistent_401_raises_auth_error_without_infinite_retry(
    settings,
) -> None:
    fake = FakePayPal()
    fake.set("POST", ORDERS_PATH, httpx.Response(401, json={"name": "INVALID_TOKEN"}))
    client = make_paypal_client(settings, fake)

    with pytest.raises(PayPalAuthError):
        await client.create_order({}, request_id="r")
    assert len(fake.requests_to("POST", ORDERS_PATH)) == 2


async def test_timeout_maps_to_timeout_error(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == OAUTH_TOKEN_PATH:
            return token_response()
        raise httpx.ReadTimeout("slow", request=request)

    http = httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL, transport=httpx.MockTransport(handler)
    )
    client = PayPalClient(settings, http_client=http)
    with pytest.raises(PayPalTimeoutError) as exc_info:
        await client.get_order(SAMPLE_ORDER_ID)
    assert exc_info.value.status_code == 504


async def test_connection_error_maps_to_api_error(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    http = httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL, transport=httpx.MockTransport(handler)
    )
    client = PayPalClient(settings, http_client=http)
    with pytest.raises(PayPalAPIError):
        await client.get_access_token()


async def test_get_order_404_raises_order_not_found(
    paypal_client: PayPalClient, fake_paypal: FakePayPal
) -> None:
    path = f"{ORDERS_PATH}/{SAMPLE_ORDER_ID}"
    fake_paypal.set(
        "GET",
        path,
        httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND", "debug_id": "abc123"}),
    )
    with pytest.raises(OrderNotFoundError) as exc_info:
        await paypal_client.get_order(SAMPLE_ORDER_ID)
    assert exc_info.value.debug_id == "abc123"


async def test_get_order_success(
    paypal_client: PayPalClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set("GET", f"{ORDERS_PATH}/{SAMPLE_ORDER_ID}", order_detail_response())
    data = await paypal_client.get_order(SAMPLE_ORDER_ID)
    assert data["status"] == "CREATED"


async def test_4xx_error_carries_debug_id_and_name(
    paypal_client: PayPalClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST",
        ORDERS_PATH,
        httpx.Response(
            422,
            json={
                "name": "UNPROCESSABLE_ENTITY",
                "debug_id": "d-1",
                "details": [{"issue": "X"}],
            },
        ),
    )
    with pytest.raises(PayPalAPIError) as exc_info:
        await paypal_client.create_order({}, request_id="r")
    err = exc_info.value
    assert err.paypal_status == 422
    assert err.paypal_name == "UNPROCESSABLE_ENTITY"
    assert err.debug_id == "d-1"
    assert "details" not in err.detail  # raw body never surfaces


async def test_5xx_error_maps_to_api_error(
    paypal_client: PayPalClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST",
        ORDERS_PATH,
        httpx.Response(500, json={"name": "INTERNAL_SERVER_ERROR", "debug_id": "x"}),
    )
    with pytest.raises(PayPalAPIError) as exc_info:
        await paypal_client.create_order({}, request_id="r")
    assert exc_info.value.status_code == 502


async def test_non_json_error_body_is_tolerated(
    paypal_client: PayPalClient, fake_paypal: FakePayPal
) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.Response(502, text="<html>Bad Gateway</html>")
    )
    with pytest.raises(PayPalAPIError):
        await paypal_client.create_order({}, request_id="r")


async def test_secrets_and_tokens_never_logged(
    paypal_client: PayPalClient,
    fake_paypal: FakePayPal,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_paypal.set(
        "POST", ORDERS_PATH, httpx.Response(201, json=created_order_response())
    )
    with caplog.at_level(logging.DEBUG):
        await paypal_client.create_order({"intent": "CAPTURE"}, request_id="r")
    assert TEST_CLIENT_SECRET not in caplog.text
    assert TEST_ACCESS_TOKEN not in caplog.text
    assert "Bearer" not in caplog.text
    assert "Basic " not in caplog.text


async def test_aclose_closes_owned_client_only(
    settings, fake_paypal: FakePayPal
) -> None:
    http = httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL, transport=fake_paypal.transport()
    )
    borrowed = PayPalClient(settings, http_client=http)
    await borrowed.aclose()
    assert not http.is_closed

    owned = PayPalClient(settings)
    await owned.aclose()
    assert owned._http.is_closed
