#!/usr/bin/env python3
"""Manual check for the Seengreat Pi Zero UPS HAT (B)."""

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
        description="Read UPS telemetry once and print the decoded values."
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
    parser.add_argument(
        "--shunt-ohms",
        type=float,
        default=None,
        help="Value (in ohms) of the INA219 shunt resistor. Defaults to FEATHERFLAP_UPTIME_SHUNT_RESISTANCE_OHMS.",
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

    shunt = args.shunt_ohms if args.shunt_ohms is not None else settings.uptime_shunt_resistance_ohms

    try:
        readings: UPSReadings = read_ups(bus_id, addresses, shunt)
    except SMBusNotAvailable:
        print("ERROR: smbus/smbus2 library is not installed.", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"ERROR: UPS read failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"ERROR: Unexpected failure reading UPS: {exc}", file=sys.stderr)
        return 1

    print()
    print(f"UPS telemetry @ address {hex(readings.address)}")
    print("-" * 36)
    print(f"{'I2C bus':<18}: {bus_id}")
    print(f"{'Bus voltage':<18}: {readings.bus_voltage_v:>8.3f} V")

    if readings.shunt_voltage_mv is not None:
        print(f"{'Shunt voltage':<18}: {readings.shunt_voltage_mv:+8.3f} mV")
    else:
        print(f"{'Shunt voltage':<18}: n/a")

    flow_labels = {
        "discharging": "Supplying load",
        "charging": "Charging battery",
        "idle": "Near zero",
        "unknown": "Current unavailable",
    }

    if readings.current_ma is not None:
        flow = flow_labels.get(readings.flow, "Current unavailable")
        current_value = abs(readings.current_ma)
        print(f"{'Current':<18}: {current_value:>8.2f} mA ({flow})")
    else:
        print(f"{'Current':<18}: n/a (set shunt value)")

    if readings.power_mw is not None and readings.current_ma is not None:
        direction = "to load" if readings.flow == "discharging" else "into battery" if readings.flow == "charging" else "minimal flow"
        power_w = abs(readings.power_mw) / 1000.0
        print(f"{'Power':<18}: {power_w:>8.3f} W ({direction})")
    elif readings.power_mw is not None:
        power_w = readings.power_mw / 1000.0
        print(f"{'Power':<18}: {power_w:>8.3f} W")
    else:
        print(f"{'Power':<18}: n/a")

    print("-" * 36)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
