"""Command-line utilities for FeatherFlap."""

from __future__ import annotations

import os
from typing import Optional

from click.core import UNSET
import typer
import uvicorn

from ..config import OperationMode, get_settings
from ..logger import configure_logging, get_logger

app = typer.Typer(add_completion=False, help="FeatherFlap diagnostics tooling.")

_BOOL_TRUE_VALUES = {"1", "true", "yes", "on"}
_BOOL_FALSE_VALUES = {"0", "false", "no", "off"}


def _parse_optional_bool(value: Optional[str]) -> Optional[bool]:
    """Convert a CLI-provided string into an optional boolean."""

    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in _BOOL_TRUE_VALUES:
        return True
    if normalized in _BOOL_FALSE_VALUES:
        return False
    raise typer.BadParameter("Expected a boolean value (true/false).")


@app.callback()
def _root_callback() -> None:
    """FeatherFlap CLI command group."""


@app.command()
def serve(
    host: Optional[str] = typer.Option(None, flag_value=UNSET, help="Interface to bind the server to."),
    port: Optional[int] = typer.Option(None, flag_value=UNSET, help="Port to bind the server to."),
    reload: Optional[str] = typer.Option(
        None,
        flag_value=UNSET,
        help="Enable auto-reload (development only). Provide true/false to override configured value.",
    ),
    log_level: Optional[str] = typer.Option(None, flag_value=UNSET, help="Logging level passed to Uvicorn."),
    mode: Optional[OperationMode] = typer.Option(None, flag_value=UNSET, case_sensitive=False, help="Override the configured operating mode (test/run)."),
) -> None:
    """Start the diagnostics API server."""

    reload_override = _parse_optional_bool(reload)
    if mode is not None:
        os.environ["FEATHERFLAP_MODE"] = mode.value
        get_settings.cache_clear()
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(__name__)
    bound_host = host or settings.host
    bound_port = port or settings.port
    logger.info(
        "Starting FeatherFlap diagnostics server (host=%s port=%s reload=%s)",
        bound_host,
        bound_port,
        reload_override if reload_override is not None else settings.reload,
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
        reload=reload_override if reload_override is not None else settings.reload,
        log_level=log_level or settings.log_level,
    )


def main() -> None:
    """Entrypoint for the ``featherflap`` console script."""

    logger = get_logger(__name__)
    logger.debug("Invoked FeatherFlap CLI entrypoint")
    app()
