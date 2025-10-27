"""Helpers for interacting with PIR motion sensors."""

from __future__ import annotations

from contextlib import suppress
from typing import Dict, Iterable

from ..logger import get_logger

logger = get_logger(__name__)


class PIRUnavailable(RuntimeError):
    """Raised when PIR sensors cannot be accessed."""


def read_pir_states(pins: Iterable[int]) -> Dict[int, int]:
    """Return the current digital states for the provided PIR sensor pins.

    Parameters
    ----------
    pins:
        Iterable of BCM pin numbers to read.

    Returns
    -------
    dict
        Mapping of pin number to GPIO state (0 or 1).
    """

    try:
        import RPi.GPIO as GPIO  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        logger.warning("RPi.GPIO not available when reading PIR sensors: %s", exc)
        raise PIRUnavailable("RPi.GPIO is not installed.") from exc

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    states: Dict[int, int] = {}
    pins = [int(pin) for pin in pins]
    logger.debug("Reading PIR sensor states for GPIO pins: %s", pins)
    try:
        for pin in pins:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            states[pin] = int(GPIO.input(pin))
    except Exception as exc:  # pragma: no cover - hardware interaction
        logger.error("Failed to read PIR sensors: %s", exc)
        raise PIRUnavailable(f"Failed to read PIR sensors: {exc}") from exc
    finally:
        for pin in pins:
            with suppress(Exception):
                GPIO.cleanup(pin)
    logger.info("PIR sensor states read successfully: %s", states)
    return states


__all__ = ["PIRUnavailable", "read_pir_states"]
