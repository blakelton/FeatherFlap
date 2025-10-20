#!/usr/bin/env python3
"""Quick check for the AHT20 temperature/humidity sensor."""

from __future__ import annotations

import argparse
import sys
import time
from _paths import add_project_src_to_path

add_project_src_to_path()

from featherflap.config import DEFAULT_AHT20_I2C_ADDRESS, get_settings
from featherflap.hardware.i2c import SMBusNotAvailable, has_smbus, open_bus


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read the AHT20 sensor once and print temperature / humidity."
    )
    parser.add_argument(
        "--bus-id",
        type=int,
        default=None,
        help="I2C bus number to probe (defaults to FEATHERFLAP_I2C_BUS_ID).",
    )
    parser.add_argument(
        "--address",
        type=lambda x: int(x, 0),
        default=None,
        help="I2C address of the AHT20 (defaults to FEATHERFLAP_AHT20_I2C_ADDRESS).",
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=5,
        help="Number of retries while waiting for the sensor to become ready (default: 5).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.01,
        help="Delay in seconds between readiness checks (default: 0.01).",
    )
    return parser.parse_args()


def read_aht20(bus, address: int, retries: int, delay: float) -> tuple[float, float]:
    bus.write_byte(address, 0xBA)  # soft reset
    time.sleep(0.02)
    bus.write_i2c_block_data(address, 0xBE, [0x08, 0x00])
    time.sleep(0.01)
    bus.write_i2c_block_data(address, 0xAC, [0x33, 0x00])
    time.sleep(0.08)

    for _ in range(max(retries, 1)):
        data = bus.read_i2c_block_data(address, 0x00, 6)
        if data[0] & 0x80:  # busy bit
            time.sleep(delay)
            continue
        raw_h = ((data[1] << 12) | (data[2] << 4) | (data[3] >> 4)) & 0xFFFFF
        raw_t = (((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]) & 0xFFFFF
        humidity = raw_h / 1048576.0 * 100.0
        temperature = raw_t / 1048576.0 * 200.0 - 50.0
        return temperature, humidity
    raise RuntimeError("AHT20 sensor busy after maximum retries.")


def main() -> int:
    args = parse_args()
    if not has_smbus():
        print("ERROR: smbus/smbus2 library is not installed.", file=sys.stderr)
        return 2

    settings = get_settings()
    bus_id = args.bus_id if args.bus_id is not None else settings.i2c_bus_id
    address = args.address if args.address is not None else settings.aht20_i2c_address

    try:
        with open_bus(bus_id) as bus:
            temperature, humidity = read_aht20(bus, address, args.retry, args.delay)
    except FileNotFoundError as exc:
        print(f"ERROR: I2C bus {bus_id} not found: {exc}", file=sys.stderr)
        return 2
    except SMBusNotAvailable:
        print("ERROR: smbus/smbus2 library is not installed.", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: AHT20 read failed: {exc}", file=sys.stderr)
        return 1

    print(f"AHT20 @ 0x{address:02X} on bus {bus_id}")
    print(f"  Temperature : {temperature:6.2f} °C")
    print(f"  Humidity    : {humidity:6.2f} %")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
