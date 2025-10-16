"""FeatherFlap – Smart bird house hardware test suite."""

from importlib.metadata import PackageNotFoundError, version

from .logger import get_logger

logger = get_logger(__name__)

try:
    __version__ = version("featherflap")
    logger.debug("Detected installed FeatherFlap version: %s", __version__)
except PackageNotFoundError:  # pragma: no cover - during local dev
    __version__ = "0.0.0"
    logger.warning("Package metadata not found; defaulting version to %s", __version__)


__all__ = ["__version__"]
