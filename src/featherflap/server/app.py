"""Application factory for the FeatherFlap diagnostics API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..config import get_settings
from ..hardware import HardwareTestRegistry, default_tests
from . import routes


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = get_settings()
    app = FastAPI(
        title="FeatherFlap Diagnostics API",
        version=__version__,
        summary="FeatherFlap hardware verification server.",
    )

    if settings.allowed_origins:
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

    app.include_router(routes.router)
    return app
