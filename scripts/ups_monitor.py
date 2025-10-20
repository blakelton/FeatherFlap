#!/usr/bin/env python3
"""Continuous UPS telemetry monitor with adaptive battery learning."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from _paths import add_project_src_to_path

add_project_src_to_path()

from featherflap.config import DEFAULT_UPTIME_I2C_ADDRESSES, get_settings
from featherflap.hardware.battery import BatteryEstimator
from featherflap.hardware.i2c import SMBusNotAvailable
from featherflap.hardware.power import read_ups
from _args import parse_int_sequence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll the UPS at intervals, log telemetry, and learn battery characteristics."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=60.0,
        help="Polling interval in seconds (default: 60).",
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
            "Ordered list of I2C addresses to try (accepts decimal or hex such as 0x43). "
            "Defaults to FEATHERFLAP_UPTIME_I2C_ADDRESSES or built-in addresses."
        ),
    )
    parser.add_argument(
        "--shunt-ohms",
        type=float,
        default=None,
        help="Value (in ohms) of the INA219 shunt resistor. Defaults to FEATHERFLAP_UPTIME_SHUNT_RESISTANCE_OHMS.",
    )
    parser.add_argument(
        "--capacity-mah",
        type=float,
        default=None,
        help="Battery capacity in milliamp-hours (defaults to FEATHERFLAP_BATTERY_CAPACITY_MAH).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Optional total run time in minutes. If omitted, runs until interrupted.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    bus_id = args.bus_id if args.bus_id is not None else settings.i2c_bus_id
    if args.addresses:
        try:
            addresses = parse_int_sequence(args.addresses, "I2C address")
        except argparse.ArgumentTypeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    elif settings.uptime_i2c_addresses:
        addresses = list(settings.uptime_i2c_addresses)
    else:
        addresses = list(DEFAULT_UPTIME_I2C_ADDRESSES)

    shunt = args.shunt_ohms if args.shunt_ohms is not None else settings.uptime_shunt_resistance_ohms
    battery_capacity = (
        args.capacity_mah if args.capacity_mah is not None else getattr(settings, "battery_capacity_mah", 10000.0)
    )
    estimator = BatteryEstimator()

    print(
        f"Polling UPS on bus {bus_id} addresses {', '.join(hex(a) for a in addresses)} "
        f"every {args.interval:.0f}s (capacity {battery_capacity:.0f} mAh). Press Ctrl+C to stop."
    )
    if args.duration:
        print(f"Will stop after approximately {args.duration} minutes.")

    stop_time = None if args.duration is None else time.time() + args.duration * 60.0

    try:
        while stop_time is None or time.time() <= stop_time:
            start = time.time()
            try:
                readings = read_ups(bus_id, addresses, shunt)
            except SMBusNotAvailable:
                print("ERROR: smbus/smbus2 library is not installed.", file=sys.stderr)
                return 2
            except RuntimeError as exc:
                print(f"{datetime.now().isoformat()} | ERROR reading UPS: {exc}", file=sys.stderr)
                time.sleep(args.interval)
                continue
            estimate = estimator.record_sample(
                timestamp=start,
                voltage_v=readings.bus_voltage_v,
                current_ma=readings.current_ma,
                flow=readings.flow,
                nominal_capacity_mah=battery_capacity,
            )

            power_w = None
            if readings.power_mw is not None and readings.current_ma is not None:
                power_w = abs(readings.power_mw) / 1000.0

            line = [
                datetime.now().isoformat(timespec="seconds"),
                f"bus={readings.bus_voltage_v:.3f}V",
                f"current={readings.current_ma:.0f}mA" if readings.current_ma is not None else "current=n/a",
                f"flow={readings.flow}",
                f"soc={estimate.soc_pct:.1f}%",
                f"capacity={estimate.capacity_mah:.0f}mAh",
            ]
            if power_w is not None:
                line.append(f"power={power_w:.2f}W")
            if estimate.time_to_empty_hours is not None:
                line.append(f"TTE={estimate.time_to_empty_hours*60:.0f}m")
            if estimate.time_to_full_hours is not None:
                line.append(f"TTF={estimate.time_to_full_hours*60:.0f}m")
            print(" | ".join(line))

            elapsed = time.time() - start
            sleep_for = max(0.0, args.interval - elapsed)
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        print("\nStopping monitor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
