"""Exclusive access coordination for camera resources."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Generator, Optional

from ..logger import get_logger

logger = get_logger(__name__)


class CameraBusyError(RuntimeError):
    """Raised when the camera is already in use."""


class _CameraLease:
    def __init__(self, owner: "CameraUsageCoordinator", purpose: str):
        self._owner = owner
        self._purpose = purpose
        self._released = False

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def release(self) -> None:
        if self._released:
            return
        self._owner._release(self._purpose)
        self._released = True


class CameraUsageCoordinator:
    """Serialize access to camera hardware across diagnostics and run mode."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._purpose: Optional[str] = None

    def acquire(self, purpose: str, *, blocking: bool = False) -> _CameraLease:
        """Obtain exclusive camera access for the given purpose."""

        if blocking:
            self._lock.acquire()
        else:
            if not self._lock.acquire(blocking=False):
                raise CameraBusyError("Camera resource is currently in use.")
        self._purpose = purpose
        logger.debug("Camera lock acquired for %s", purpose)
        return _CameraLease(self, purpose)

    def _release(self, purpose: str) -> None:
        """Internal release helper invoked by leases."""

        if self._purpose != purpose:
            logger.warning("Camera lock release mismatch (expected %s, actual %s)", self._purpose, purpose)
        self._purpose = None
        self._lock.release()
        logger.debug("Camera lock released for %s", purpose)

    def in_use(self) -> Optional[str]:
        """Return the current purpose holding the lock, if any."""

        return self._purpose
