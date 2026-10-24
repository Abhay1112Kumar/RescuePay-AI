"""Health check API endpoint router."""

from fastapi import APIRouter, Depends, status

from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Returns service operational status, application name, and version.",
)
@router.get(
    "/",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def check_health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Verify backend operational status without external dependencies."""
    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        version="0.1.0",
    )
