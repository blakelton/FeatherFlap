#!/usr/bin/env python3
"""Manual check for the AHT20 and BMP280 environmental sensors."""

from __future__ import annotations

import argparse
import sys

from featherflap.config import (
    DEFAULT_AHT20_I2C_ADDRESS,
    DEFAULT_BMP280_I2C_ADDRESS,
    get_settings,
)
from featherflap.hardware.i2c import SMBusNotAvailable
from featherflap.hardware.sensors import EnvironmentSnapshot, read_environment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read the AHT20 and BMP280 sensors once and print the captured values."
    )
    parser.add_argument(
        "--bus-id",
        type=int,
        default=None,
        help="I2C bus number to probe (defaults to FEATHERFLAP_I2C_BUS_ID).",
    )
    parser.add_argument(
        "--aht20-address",
        type=lambda value: int(value, 0),
        default=None,
        help="I2C address for the AHT20 sensor (defaults to FEATHERFLAP_AHT20_I2C_ADDRESS).",
    )
    parser.add_argument(
        "--bmp280-address",
        type=lambda value: int(value, 0),
        default=None,
        help="I2C address for the BMP280 sensor (defaults to FEATHERFLAP_BMP280_I2C_ADDRESS).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    bus_id = args.bus_id if args.bus_id is not None else settings.i2c_bus_id
    aht20_address = (
        args.aht20_address
        if args.aht20_address is not None
        else settings.aht20_i2c_address or DEFAULT_AHT20_I2C_ADDRESS
    )
    bmp280_address = (
        args.bmp280_address
        if args.bmp280_address is not None
        else settings.bmp280_i2c_address or DEFAULT_BMP280_I2C_ADDRESS
    )

    try:
        snapshot: EnvironmentSnapshot = read_environment(bus_id, aht20_address, bmp280_address)
    except SMBusNotAvailable:
        print("ERROR: smbus/smbus2 library is not installed.", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"ERROR: Sensor read failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"ERROR: Unexpected failure reading environmental sensors: {exc}", file=sys.stderr)
        return 1

    if snapshot.results:
        print("Sensor results:")
        for sensor, values in snapshot.results.items():
            print(f"  {sensor}:")
            for name, value in values.items():
                print(f"    {name}: {value}")
    else:
        print("No sensor readings available.")

    if snapshot.errors:
        print("Sensor errors detected:", file=sys.stderr)
        for sensor, error in snapshot.errors.items():
            print(f"  {sensor}: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
