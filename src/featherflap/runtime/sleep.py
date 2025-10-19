"""Utilities for handling quiet windows (sleep mode) in run mode."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Iterable, List

from ..logger import get_logger

logger = get_logger(__name__)


def _parse_time(value: str) -> time:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time value: {value!r}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Time out of range: {value!r}")
    return time(hour=hour, minute=minute)


@dataclass(frozen=True)
class SleepWindow:
    """Inclusive-exclusive window representing quiet hours."""

    start: time
    end: time

    def contains(self, value: time) -> bool:
        if self.start <= self.end:
            return self.start <= value < self.end
        return value >= self.start or value < self.end


class SleepScheduler:
    """Determine whether the system should be in a low-power state."""

    def __init__(self, windows: Iterable[dict[str, str]]):
        self._windows: List[SleepWindow] = []
        for window in windows:
            try:
                start = _parse_time(window["start"])
                end = _parse_time(window["end"])
            except (KeyError, ValueError) as exc:
                logger.error("Invalid sleep window specification %s: %s", window, exc)
                continue
            self._windows.append(SleepWindow(start=start, end=end))
        if self._windows:
            logger.info("Configured %d sleep windows", len(self._windows))
        else:
            logger.debug("No sleep windows configured")

    def is_sleep_time(self, now: datetime | None = None) -> bool:
        """Return True when the current time falls inside any quiet window."""

        if not self._windows:
            return False
        current = (now or datetime.now()).time()
        return any(window.contains(current) for window in self._windows)
