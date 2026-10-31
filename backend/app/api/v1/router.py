"""API v1 central router aggregating all modular endpoints."""

from fastapi import APIRouter

from app.api.v1 import health, payments, sandbox, webhooks

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_router.include_router(sandbox.router, prefix="/sandbox", tags=["sandbox"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
