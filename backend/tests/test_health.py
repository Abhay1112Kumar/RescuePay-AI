"""Tests for the health check API endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Fixture providing a FastAPI TestClient."""
    return TestClient(app)


def test_health_check_returns_200(client: TestClient) -> None:
    """Verify /api/v1/health returns HTTP 200 OK."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_check_json_structure(client: TestClient) -> None:
    """Verify response payload matches the expected JSON structure exactly."""
    response = client.get("/api/v1/health")
    data = response.json()
    assert data == {
        "status": "ok",
        "service": "RescuePay-AI",
        "version": "0.1.0",
    }


def test_health_check_content_type(client: TestClient) -> None:
    """Verify response headers declare application/json Content-Type."""
    response = client.get("/api/v1/health")
    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type


def test_health_check_works_without_paypal_credentials(client: TestClient) -> None:
    """Verify health endpoint functions properly when no PayPal credentials exist."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_invalid_route_returns_404(client: TestClient) -> None:
    """Verify requesting an invalid route produces HTTP 404 Not Found."""
    response = client.get("/api/v1/nonexistent-route")
    assert response.status_code == 404
