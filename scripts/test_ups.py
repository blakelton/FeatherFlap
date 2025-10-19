#!/usr/bin/env python3
"""Manual check for the PiZ-UpTime UPS HAT."""

from __future__ import annotations

import argparse
import sys
from _paths import add_project_src_to_path

add_project_src_to_path()

from featherflap.config import DEFAULT_UPTIME_I2C_ADDRESSES, get_settings
from featherflap.hardware.i2c import SMBusNotAvailable
from featherflap.hardware.power import UPSReadings, read_ups
from _args import parse_int_sequence


def parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(
        description="Read the PiZ-UpTime UPS telemetry once and print the decoded values."
    )
    parser.add_argument(
        "--bus-id",
        type=int,
        default=None,
        help="I2C bus number to probe (defaults to FEATHERFLAP_I2C_BUS_ID).",
    )
    parser.add_argument(
        "--addresses",
        nargs="+",
        type=str,
        default=None,
        help=(
            "Ordered list of I2C addresses to try (accepts decimal or hex such as 0x48). "
            "Defaults to FEATHERFLAP_UPTIME_I2C_ADDRESSES or built-in addresses."
        ),
    )
    return parser, parser.parse_args()


def main() -> int:
    parser, args = parse_args()
    settings = get_settings()
    bus_id = args.bus_id if args.bus_id is not None else settings.i2c_bus_id
    if args.addresses:
        try:
            addresses = parse_int_sequence(args.addresses, "I2C address")
        except argparse.ArgumentTypeError as exc:
            parser.error(str(exc))
    elif settings.uptime_i2c_addresses:
        addresses = list(settings.uptime_i2c_addresses)
    else:
        addresses = list(DEFAULT_UPTIME_I2C_ADDRESSES)

    try:
        readings: UPSReadings = read_ups(bus_id, addresses)
    except SMBusNotAvailable:
        print("ERROR: smbus/smbus2 library is not installed.", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"ERROR: UPS read failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"ERROR: Unexpected failure reading UPS: {exc}", file=sys.stderr)
        return 1

    data = readings.to_dict()
    print("UPS telemetry:")
    for key in ("address", "vin", "vout", "vbat", "temperature_c"):
        if key in data:
            print(f"  {key}: {data[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
