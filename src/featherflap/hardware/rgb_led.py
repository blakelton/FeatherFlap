"""Helpers for controlling the RGB LED assembly."""

from __future__ import annotations

import time
from contextlib import suppress
from typing import Iterable, Tuple

from ..logger import get_logger

logger = get_logger(__name__)


class RGBLedUnavailable(RuntimeError):
    """Raised when the RGB LED cannot be controlled."""


def _import_gpio():
    try:
        import RPi.GPIO as GPIO  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        logger.warning("RPi.GPIO not available for RGB LED control: %s", exc)
        raise RGBLedUnavailable("RPi.GPIO is not installed.") from exc
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    return GPIO


def flash_rgb_led_sequence(
    pins: Iterable[int],
    delay_seconds: float,
) -> None:
    """Flash each RGB LED pin sequentially."""

    pins = tuple(int(pin) for pin in pins)
    GPIO = _import_gpio()
    logger.debug("Flashing RGB LED sequence on pins %s", pins)
    try:
        for pin in pins:
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
        for pin in pins:
            GPIO.output(pin, GPIO.HIGH)
            time.sleep(delay_seconds)
            GPIO.output(pin, GPIO.LOW)
    except Exception as exc:  # pragma: no cover - hardware interaction
        logger.error("RGB LED sequence failed: %s", exc)
        raise RGBLedUnavailable(f"Failed to toggle RGB LED pins: {exc}") from exc
    finally:
        for pin in pins:
            with suppress(Exception):
                GPIO.cleanup(pin)
    logger.info("RGB LED sequence completed on pins %s", pins)


def set_rgb_led_color(
    pins: Tuple[int, int, int],
    red: int,
    green: int,
    blue: int,
    hold_seconds: float = 1.0,
) -> None:
    """Set the RGB LED color and hold it briefly.

    Color components are treated as boolean intensity: any value > 0 energizes
    the corresponding channel.
    """

    r_pin, g_pin, b_pin = (int(pin) for pin in pins)
    GPIO = _import_gpio()
    logger.debug(
        "Setting RGB LED color (pins=%s, R=%d, G=%d, B=%d, hold=%.2fs)",
        pins,
        red,
        green,
        blue,
        hold_seconds,
    )
    states = {
        r_pin: GPIO.HIGH if red > 0 else GPIO.LOW,
        g_pin: GPIO.HIGH if green > 0 else GPIO.LOW,
        b_pin: GPIO.HIGH if blue > 0 else GPIO.LOW,
    }
    try:
        for pin, state in states.items():
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
            GPIO.output(pin, state)
        if hold_seconds > 0:
            time.sleep(max(0.0, hold_seconds))
    except Exception as exc:  # pragma: no cover - hardware interaction
        logger.error("RGB LED color set failed: %s", exc)
        raise RGBLedUnavailable(f"Failed to set RGB LED color: {exc}") from exc
    finally:
        for pin in (r_pin, g_pin, b_pin):
            with suppress(Exception):
                GPIO.output(pin, GPIO.LOW)
                GPIO.cleanup(pin)
    logger.info("RGB LED color applied successfully")


__all__ = ["RGBLedUnavailable", "flash_rgb_led_sequence", "set_rgb_led_color"]
