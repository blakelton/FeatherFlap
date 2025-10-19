"""Inter-process coordination for mutually-exclusive operating modes."""

from __future__ import annotations

import atexit
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from ..config import OperationMode
from ..logger import get_logger

logger = get_logger(__name__)
MODE_FILE = Path(os.getenv("FEATHERFLAP_MODE_FILE", Path(os.getenv("TMPDIR", "/tmp")) / "featherflap_mode.json"))


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class ModeRegistry:
    """Ensure only one operating mode (test or run) is active at a time."""

    def __init__(self, lock_path: Path = MODE_FILE):
        self._path = lock_path
        self._acquired = False
        self._pid = os.getpid()

    def acquire(self, mode: OperationMode) -> None:
        """Record the requested mode, raising if a conflicting active mode exists."""

        existing = self._read()
        if existing:
            existing_mode = existing.get("mode")
            existing_pid = existing.get("pid")
            if existing_pid and not _pid_alive(existing_pid):
                logger.warning("Removing stale mode file for inactive pid %s", existing_pid)
                self._path.unlink(missing_ok=True)
            elif existing_mode and existing_mode != mode.value:
                raise RuntimeError(
                    f"FeatherFlap is already running in {existing_mode} mode (pid={existing_pid}). "
                    f"Stop the other process before starting {mode.value} mode."
                )
            elif existing_mode == mode.value and existing_pid == self._pid:
                logger.debug("Mode %s already acquired by this process", mode.value)
                self._acquired = True
                atexit.register(self.release)
                return

        payload = {
            "mode": mode.value,
            "pid": self._pid,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._path.write_text(json.dumps(payload, indent=2))
        self._acquired = True
        atexit.register(self.release)

    def release(self) -> None:
        """Clear the mode lock if held by this process."""

        if not self._acquired:
            return
        data = self._read()
        if data and data.get("pid") != self._pid:
            # Another process has taken over.
            logger.debug("Skipping mode release; another process acquired the registry")
            self._acquired = False
            return
        self._path.unlink(missing_ok=True)
        self._acquired = False

    def _read(self) -> Optional[dict]:
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text())
        except json.JSONDecodeError:
            logger.warning("Mode file %s was corrupted; removing", self._path)
            self._path.unlink(missing_ok=True)
            return None
