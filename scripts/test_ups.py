#!/usr/bin/env python3
"""Manual check for the Seengreat Pi Zero UPS HAT (B)."""

from __future__ import annotations

import argparse
import math
import os
import sys
from _paths import add_project_src_to_path

add_project_src_to_path()

from featherflap.config import DEFAULT_UPTIME_I2C_ADDRESSES, get_settings
from featherflap.hardware.battery import BatteryEstimator
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
    parser.add_argument(
        "--capacity-mah",
        type=float,
        default=10000.0,
        help="Battery capacity in milliamp-hours (default: 10000 for the Seengreat 10Ah pack).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colour output (overrides NO_COLOR environment variable).",
    )
    return parser, parser.parse_args()


class Palette:
    """Lightweight ANSI colour palette."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.reset = "\033[0m" if enabled else ""
        self.bold = "\033[1m" if enabled else ""
        self.cyan = "\033[36m" if enabled else ""
        self.magenta = "\033[35m" if enabled else ""
        self.green = "\033[32m" if enabled else ""
        self.yellow = "\033[33m" if enabled else ""
        self.red = "\033[31m" if enabled else ""
        self.blue = "\033[34m" if enabled else ""
        self.dim = "\033[2m" if enabled else ""

    def wrap(self, text: str, *styles: str) -> str:
        if not self.enabled or not styles:
            return text
        prefix = "".join(styles)
        return f"{prefix}{text}{self.reset}"


def _supports_color(args: argparse.Namespace) -> bool:
    if args.no_color:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def format_duration(hours: float) -> str:
    if not math.isfinite(hours) or hours <= 0:
        return "n/a"
    total_minutes = int(round(hours * 60))
    if total_minutes <= 0:
        return "~0m"
    hours_part, minutes = divmod(total_minutes, 60)
    days, hours_only = divmod(hours_part, 24)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours_only:
        parts.append(f"{hours_only}h")
    if minutes and (not days or len(parts) < 2):
        parts.append(f"{minutes}m")
    if not parts:
        return "~0m"
    return " ".join(parts[:2])


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

    palette = Palette(_supports_color(args))
    estimator = BatteryEstimator()
    estimate = estimator.record_sample(
        timestamp=None,
        voltage_v=readings.bus_voltage_v,
        current_ma=readings.current_ma,
        flow=readings.flow,
        nominal_capacity_mah=args.capacity_mah,
    )

    capacity_mah = estimate.capacity_mah
    soc_pct = estimate.soc_pct
    time_to_empty_hours = estimate.time_to_empty_hours
    time_to_full_hours = estimate.time_to_full_hours

    def fmt_label(text: str) -> str:
        raw = f"{text:<18}"
        return palette.wrap(raw, palette.bold)

    flow_labels = {
        "discharging": "Supplying load",
        "charging": "Charging battery",
        "idle": "Near zero",
        "unknown": "Current unavailable",
    }
    flow_colours = {
        "discharging": palette.green,
        "charging": palette.yellow,
        "idle": palette.cyan,
        "unknown": palette.dim,
    }

    soc_colour = palette.green if soc_pct >= 80 else palette.yellow if soc_pct >= 40 else palette.red

    print()
    heading = f"UPS telemetry @ address {hex(readings.address)}"
    print(palette.wrap(heading, palette.bold, palette.blue))
    separator = palette.wrap("-" * 40, palette.dim)
    print(separator)
    print(f"{fmt_label('I2C bus')}: {palette.wrap(str(bus_id), palette.cyan)}")
    print(f"{fmt_label('Bus voltage')}: {palette.wrap(f'{readings.bus_voltage_v:>8.3f} V', palette.magenta)}")

    if readings.shunt_voltage_mv is not None:
        print(f"{fmt_label('Shunt voltage')}: {palette.wrap(f'{readings.shunt_voltage_mv:+8.3f} mV', palette.cyan)}")
    else:
        print(f"{fmt_label('Shunt voltage')}: {palette.wrap('n/a', palette.dim)}")

    if readings.current_ma is not None:
        flow_text = flow_labels.get(readings.flow, "Current unavailable")
        flow_colour = flow_colours.get(readings.flow, palette.dim)
        current_value = abs(readings.current_ma)
        current_str = f"{current_value:>8.2f} mA"
        print(
            f"{fmt_label('Current')}: "
            f"{palette.wrap(current_str, palette.green)} "
            f"({palette.wrap(flow_text, flow_colour)})"
        )
    else:
        print(f"{fmt_label('Current')}: {palette.wrap('n/a', palette.dim)} {palette.wrap('(set shunt value)', palette.dim)}")

    if readings.power_mw is not None and readings.current_ma is not None:
        direction = (
            "to load"
            if readings.flow == "discharging"
            else "into battery"
            if readings.flow == "charging"
            else "minimal flow"
        )
        direction_colour = flow_colours.get(readings.flow, palette.dim)
        power_w = abs(readings.power_mw) / 1000.0
        print(
            f"{fmt_label('Power')}: "
            f"{palette.wrap(f'{power_w:>8.3f} W', palette.magenta)} "
            f"({palette.wrap(direction, direction_colour)})"
        )
    elif readings.power_mw is not None:
        power_w = readings.power_mw / 1000.0
        print(f"{fmt_label('Power')}: {palette.wrap(f'{power_w:>8.3f} W', palette.magenta)}")
    else:
        print(f"{fmt_label('Power')}: {palette.wrap('n/a', palette.dim)}")

    soc_extra_parts = [f"voltage {estimate.voltage_soc_pct:.1f}%"]
    if estimate.coulomb_soc_pct is not None:
        soc_extra_parts.append(f"learned {estimate.coulomb_soc_pct:.1f}%")
    soc_extra = "; ".join(soc_extra_parts)
    print(f"{fmt_label('Battery SoC')}: {palette.wrap(f'{soc_pct:>8.1f} %', soc_colour)} ({soc_extra})")

    capacity_colour = palette.green if capacity_mah >= args.capacity_mah * 0.95 else palette.yellow
    if capacity_mah < args.capacity_mah * 0.6:
        capacity_colour = palette.red
    print(
        f"{fmt_label('Capacity est.')}: "
        f"{palette.wrap(f'{capacity_mah:>8.0f} mAh', capacity_colour)} "
        f"(nominal {args.capacity_mah:.0f} mAh)"
    )

    if time_to_empty_hours is not None:
        eta = format_duration(time_to_empty_hours)
        print(f"{fmt_label('Est. time remaining')}: {palette.wrap(eta, palette.green)}")
    if time_to_full_hours is not None:
        eta = format_duration(time_to_full_hours)
        print(f"{fmt_label('Est. time to full')}: {palette.wrap(eta, palette.yellow)}")
    if time_to_empty_hours is None and time_to_full_hours is None:
        print(f"{fmt_label('Runtime estimate')}: {palette.wrap('n/a (insufficient current)', palette.dim)}")

    print(
        f"{fmt_label('History samples')}: "
        f"{palette.wrap(str(estimate.samples_recorded), palette.cyan)}"
    )

    print(separator)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
