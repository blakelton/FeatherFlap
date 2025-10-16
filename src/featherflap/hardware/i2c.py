"""Shared helpers for working with the Raspberry Pi I²C bus."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

try:  # pragma: no cover - optional dependency
    from smbus2 import SMBus  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    try:
        from smbus import SMBus  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
        SMBus = None  # type: ignore


class SMBusNotAvailable(RuntimeError):
    """Raised when the smbus/smbus2 library is not installed."""


@contextmanager
def open_bus(bus_id: int) -> Iterator["SMBus"]:
    """Context manager yielding an I²C bus instance."""

    if SMBus is None:
        raise SMBusNotAvailable("smbus/smbus2 library is not installed.")
    bus = SMBus(bus_id)
    try:
        yield bus
    finally:
        bus.close()


def has_smbus() -> bool:
    """Return True if an SMBus implementation is importable."""

    return SMBus is not None
