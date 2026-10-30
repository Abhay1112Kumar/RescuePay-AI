"""Main entry point for the RescuePay-AI FastAPI application."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import Database


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Optionally create tables for local dev; release shared resources on shutdown."""
    settings = get_settings()
    if settings.DATABASE_AUTO_CREATE:
        database = getattr(
            application.state, "database", None
        ) or Database.from_settings(settings)
        application.state.database = database
        await database.create_all()

    yield

    client = getattr(application.state, "paypal_client", None)
    if client is not None:
        await client.aclose()
        application.state.paypal_client = None
    database = getattr(application.state, "database", None)
    if database is not None:
        await database.dispose()
        application.state.database = None


def create_application() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    settings = get_settings()
    configure_logging(settings)

    application = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        description=(
            "Production-grade FastAPI backend for the RescuePay-AI "
            "payment integration system."
        ),
        lifespan=lifespan,
    )

    # Controlled CORS: avoid permissive wildcards with credentials
    if settings.DEBUG:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    register_exception_handlers(application)

    # Register API v1 router prefix
    application.include_router(api_router, prefix=settings.API_V1_STR)

    @application.get("/", tags=["root"], include_in_schema=False)
    def root():
        """Root status check endpoint."""
        return {
            "name": settings.APP_NAME,
            "version": __version__,
            "docs": "/docs",
            "health": f"{settings.API_V1_STR}/health",
        }

    return application


app = create_application()
