"""Command-line utilities for FeatherFlap."""

from __future__ import annotations

from typing import Optional

import typer
import uvicorn

from ..config import get_settings
from ..logger import configure_logging, get_logger

app = typer.Typer(add_completion=False, help="FeatherFlap diagnostics tooling.")


@app.command()
def serve(
    host: Optional[str] = typer.Option(None, help="Interface to bind the server to."),
    port: Optional[int] = typer.Option(None, help="Port to bind the server to."),
    reload: Optional[bool] = typer.Option(None, help="Enable auto-reload (development only)."),
    log_level: Optional[str] = typer.Option(None, help="Logging level passed to Uvicorn."),
) -> None:
    """Start the diagnostics API server."""

    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(__name__)
    bound_host = host or settings.host
    bound_port = port or settings.port
    logger.info(
        "Starting FeatherFlap diagnostics server (host=%s port=%s reload=%s)",
        bound_host,
        bound_port,
        reload if reload is not None else settings.reload,
    )
    logger.debug(
        "Logging toggles - error=%s warning=%s info=%s debug=%s",
        settings.log_error_enabled,
        settings.log_warning_enabled,
        settings.log_info_enabled,
        settings.log_debug_enabled,
    )
    uvicorn.run(
        "featherflap.server.app:create_application",
        factory=True,
        host=host or settings.host,
        port=port or settings.port,
        reload=reload if reload is not None else settings.reload,
        log_level=log_level or settings.log_level,
    )


def main() -> None:
    """Entrypoint for the ``featherflap`` console script."""

    logger = get_logger(__name__)
    logger.debug("Invoked FeatherFlap CLI entrypoint")
    app()
