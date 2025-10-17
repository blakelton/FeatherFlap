#!/usr/bin/env python3
"""Manual check for the Raspberry Pi I2C bus."""

from __future__ import annotations

import argparse
import sys

from featherflap.config import get_settings
from featherflap.hardware.i2c import SMBusNotAvailable, open_bus


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open the configured Raspberry Pi I2C bus to verify the smbus stack and kernel device are available."
    )
    parser.add_argument(
        "--bus-id",
        type=int,
        default=None,
        help="I2C bus number to probe (defaults to FEATHERFLAP_I2C_BUS_ID).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    bus_id = args.bus_id if args.bus_id is not None else settings.i2c_bus_id

    try:
        with open_bus(bus_id):
            print(f"I2C bus {bus_id} opened successfully.")
            return 0
    except SMBusNotAvailable:
        print("ERROR: smbus/smbus2 library is not installed.", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"ERROR: I2C bus {bus_id} not found: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"ERROR: Unexpected failure opening I2C bus {bus_id}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
