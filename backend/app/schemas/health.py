"""Pydantic schema for health check endpoint response."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response payload schema."""

    status: str = Field(default="ok", description="Operational status of the service")
    service: str = Field(default="RescuePay-AI", description="Service application name")
    version: str = Field(default="0.1.0", description="API version")
