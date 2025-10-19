"""Application factory for the FeatherFlap diagnostics API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..config import OperationMode, get_settings
from ..hardware import HardwareTestRegistry, default_tests
from ..logger import configure_logging, get_logger
from ..runtime import CameraUsageCoordinator, ModeRegistry, RunModeController
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

    mode_registry = ModeRegistry()
    mode_registry.acquire(settings.mode)
    app.state.mode_registry = mode_registry
    app.state.operation_mode = settings.mode
    app.state.settings = settings

    camera_coordinator: CameraUsageCoordinator | None = None
    run_controller: RunModeController | None = None
    if settings.mode == OperationMode.RUN:
        camera_coordinator = CameraUsageCoordinator()
        run_controller = RunModeController(settings, camera_coordinator)
        app.state.camera_coordinator = camera_coordinator
        app.state.run_controller = run_controller

        @app.on_event("startup")
        async def _start_run_mode() -> None:  # pragma: no cover - integration path
            run_controller.start()

        @app.on_event("shutdown")
        async def _stop_run_mode() -> None:  # pragma: no cover - integration path
            run_controller.stop()
    else:
        app.state.camera_coordinator = None
        app.state.run_controller = None

    registry = HardwareTestRegistry()
    registry.extend(default_tests())
    app.state.registry = registry
    logger.info("Registered %d hardware diagnostics", len(registry.tests))

    app.include_router(routes.router)
    logger.debug("API routes registered")

    @app.on_event("shutdown")
    async def _release_mode() -> None:  # pragma: no cover - integration path
        mode_registry.release()

    return app
