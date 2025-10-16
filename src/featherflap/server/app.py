"""Application factory for the FeatherFlap diagnostics API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..config import get_settings
from ..hardware import HardwareTestRegistry, default_tests
from ..logger import configure_logging, get_logger
from . import routes


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(__name__)
    logger.info(
        "Initialising FeatherFlap FastAPI application (host=%s port=%s reload=%s)",
        settings.host,
        settings.port,
        settings.reload,
    )
    app = FastAPI(
        title="FeatherFlap Diagnostics API",
        version=__version__,
        summary="FeatherFlap hardware verification server.",
    )

    if settings.allowed_origins:
        logger.debug("Configuring CORS with allowed origins: %s", settings.allowed_origins)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )

    registry = HardwareTestRegistry()
    registry.extend(default_tests())
    app.state.registry = registry
    logger.info("Registered %d hardware diagnostics", len(registry.tests))

    app.include_router(routes.router)
    logger.debug("API routes registered")
    return app
