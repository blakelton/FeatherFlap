#!/usr/bin/env python3
"""Manual check for PIR motion sensors wired to GPIO inputs."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Dict

from _paths import add_project_src_to_path

add_project_src_to_path()

from featherflap.config import get_settings
from _args import parse_int_sequence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll the configured PIR GPIO inputs and print their HIGH/LOW state."
    )
    parser.add_argument(
        "--pins",
        nargs="+",
        default=None,
        help="GPIO numbers (BCM) to probe. Defaults to FEATHERFLAP_PIR_PINS.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=1,
        help="How many times to poll the sensors (default: 1).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Seconds to wait between samples (default: 0.5).",
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
        pins = list(settings.pir_pins)
    if not pins:
        print("ERROR: No PIR pins configured.", file=sys.stderr)
        return 1

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    states: Dict[int, int] = {}
    try:
        for pin in pins:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        for sample in range(max(1, args.samples)):
            states.clear()
            for pin in pins:
                states[pin] = GPIO.input(pin)
            print(f"Sample {sample + 1}:")
            for pin in pins:
                level = "HIGH" if states[pin] else "LOW"
                print(f"  GPIO{pin}: {level}")
            if sample + 1 < args.samples:
                time.sleep(max(0.0, args.interval))
    except Exception as exc:
        print(f"ERROR: Failed to read PIR sensors: {exc}", file=sys.stderr)
        return 1
    finally:
        for pin in pins:
            try:
                GPIO.cleanup(pin)
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
