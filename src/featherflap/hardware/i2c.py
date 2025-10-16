"""Shared helpers for working with the Raspberry Pi I²C bus."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from ..logger import get_logger

try:  # pragma: no cover - optional dependency
    from smbus2 import SMBus  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    try:
        from smbus import SMBus  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
        SMBus = None  # type: ignore

logger = get_logger(__name__)


class SMBusNotAvailable(RuntimeError):
    """Raised when the smbus/smbus2 library is not installed."""


@contextmanager
def open_bus(bus_id: int) -> Iterator["SMBus"]:
    """Context manager yielding an I²C bus instance."""

    if SMBus is None:
        logger.error("Attempted to open I²C bus %s without smbus support", bus_id)
        raise SMBusNotAvailable("smbus/smbus2 library is not installed.")
    logger.debug("Opening I²C bus %s", bus_id)
    bus = SMBus(bus_id)
    try:
        yield bus
    finally:
        logger.debug("Closing I²C bus %s", bus_id)
        bus.close()


def has_smbus() -> bool:
    """Return True if an SMBus implementation is importable."""

    available = SMBus is not None
    logger.debug("SMBus availability check: %s", available)
    return available
