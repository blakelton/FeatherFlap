"""Server application for FeatherFlap."""

from ..logger import get_logger
from .app import create_application

get_logger(__name__).debug("Server package initialised")

__all__ = ["create_application"]
