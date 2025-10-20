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
from featherflap.hardware.i2c import SMBusNotAvailable
from featherflap.hardware.power import UPSReadings, read_ups
from _args import parse_int_sequence

BATTERY_SOC_CURVE = [
    (4.20, 100.0),
    (4.15, 98.0),
    (4.12, 95.0),
    (4.10, 93.0),
    (4.05, 90.0),
    (4.00, 80.0),
    (3.95, 72.0),
    (3.92, 65.0),
    (3.90, 60.0),
    (3.87, 55.0),
    (3.84, 50.0),
    (3.80, 45.0),
    (3.78, 40.0),
    (3.75, 35.0),
    (3.72, 30.0),
    (3.70, 27.0),
    (3.68, 24.0),
    (3.65, 20.0),
    (3.60, 15.0),
    (3.55, 10.0),
    (3.50, 6.0),
    (3.45, 3.0),
    (3.40, 1.0),
    (3.35, 0.0),
]

MIN_CURRENT_FOR_RUNTIME_A = 0.05  # 50 mA threshold for timing estimates


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


def estimate_state_of_charge(voltage: float) -> float:
    curve = BATTERY_SOC_CURVE
    if voltage >= curve[0][0]:
        return 100.0
    if voltage <= curve[-1][0]:
        return 0.0
    for (v_hi, soc_hi), (v_lo, soc_lo) in zip(curve, curve[1:]):
        if v_lo <= voltage <= v_hi:
            span = v_hi - v_lo
            if span <= 0:
                return soc_lo
            fraction = (voltage - v_lo) / span
            return soc_lo + fraction * (soc_hi - soc_lo)
    return max(0.0, min(100.0, curve[-1][1]))


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


def compute_runtime_estimates(
    readings: UPSReadings,
    soc_pct: float,
    capacity_mah: float,
) -> tuple[float | None, float | None]:
    if readings.current_ma is None or capacity_mah <= 0:
        return None, None
    capacity_ah = capacity_mah / 1000.0
    net_current_a = readings.current_ma / 1000.0
    energy_available_ah = capacity_ah * (soc_pct / 100.0)
    energy_missing_ah = capacity_ah * max(0.0, 1.0 - soc_pct / 100.0)

    time_to_empty = None
    time_to_full = None

    if readings.flow == "discharging":
        discharge_current_a = abs(net_current_a)
        if discharge_current_a >= MIN_CURRENT_FOR_RUNTIME_A and energy_available_ah > 0:
            time_to_empty = energy_available_ah / discharge_current_a
    elif readings.flow == "charging":
        charge_current_a = max(net_current_a, 0.0)
        if charge_current_a >= MIN_CURRENT_FOR_RUNTIME_A and energy_missing_ah > 0:
            time_to_full = energy_missing_ah / charge_current_a

    return time_to_empty, time_to_full


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

    soc_pct = estimate_state_of_charge(readings.bus_voltage_v)
    time_to_empty_hours, time_to_full_hours = compute_runtime_estimates(readings, soc_pct, args.capacity_mah)

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

    print(f"{fmt_label('Battery SoC')}: {palette.wrap(f'{soc_pct:>8.1f} %', soc_colour)}")

    if time_to_empty_hours is not None:
        eta = format_duration(time_to_empty_hours)
        print(f"{fmt_label('Est. time remaining')}: {palette.wrap(eta, palette.green)}")
    if time_to_full_hours is not None:
        eta = format_duration(time_to_full_hours)
        print(f"{fmt_label('Est. time to full')}: {palette.wrap(eta, palette.yellow)}")
    if time_to_empty_hours is None and time_to_full_hours is None:
        print(f"{fmt_label('Runtime estimate')}: {palette.wrap('n/a (insufficient current)', palette.dim)}")

    print(separator)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
