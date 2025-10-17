#!/usr/bin/env python3
"""Manual check for the RGB LED outputs."""

from __future__ import annotations

import argparse
import sys
import time

from _paths import add_project_src_to_path

add_project_src_to_path()

from featherflap.config import get_settings
from _args import parse_int_sequence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Toggle each RGB LED GPIO output sequentially to validate wiring."
    )
    parser.add_argument(
        "--pins",
        nargs="+",
        default=None,
        help="GPIO numbers (BCM) in the order they should flash. Defaults to FEATHERFLAP_RGB_LED_PINS.",
    )
    parser.add_argument(
        "--hold",
        type=float,
        default=0.15,
        help="Seconds to hold each channel HIGH before turning it back off (default: 0.15).",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help="How many times to cycle across the channels (default: 1).",
    )
    return parser.parse_args()


def main() -> int:
    try:
        import RPi.GPIO as GPIO  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        print("ERROR: RPi.GPIO is not installed. Install python3-rpi.gpio on Raspberry Pi OS.", file=sys.stderr)
        return 2

    args = parse_args()
    settings = get_settings()
    if args.pins:
        try:
            pins = parse_int_sequence(args.pins, "GPIO number")
        except argparse.ArgumentTypeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    else:
        pins = list(settings.rgb_led_pins)
    if not pins:
        print("ERROR: No RGB LED pins configured.", file=sys.stderr)
        return 1

    hold = max(0.0, args.hold)
    rounds = max(1, args.rounds)

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    try:
        for pin in pins:
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
        for round_index in range(rounds):
            print(f"Round {round_index + 1} of {rounds}")
            for pin in pins:
                print(f"  Driving GPIO{pin} HIGH")
                GPIO.output(pin, GPIO.HIGH)
                time.sleep(hold)
                GPIO.output(pin, GPIO.LOW)
    except Exception as exc:
        print(f"ERROR: Failed to toggle RGB LED pins: {exc}", file=sys.stderr)
        return 1
    finally:
        for pin in pins:
            try:
                GPIO.cleanup(pin)
            except Exception:
                pass

    print("RGB LED cycle completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
