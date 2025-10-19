#!/usr/bin/env python3
"""Manual check for the Seengreat Pi Zero UPS HAT (B)."""

from __future__ import annotations

import argparse
import os
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

    print()
    heading = f"UPS telemetry @ address {hex(readings.address)}"
    print(palette.wrap(heading, palette.bold, palette.blue))
    separator = palette.wrap("-" * 36, palette.dim)
    print(separator)
    print(f"{palette.wrap('I2C bus', palette.bold):<18}: {palette.wrap(str(bus_id), palette.cyan)}")
    print(
        f"{palette.wrap('Bus voltage', palette.bold):<18}: "
        f"{palette.wrap(f'{readings.bus_voltage_v:>8.3f} V', palette.magenta)}"
    )

    if readings.shunt_voltage_mv is not None:
        print(
            f"{palette.wrap('Shunt voltage', palette.bold):<18}: "
            f"{palette.wrap(f'{readings.shunt_voltage_mv:+8.3f} mV', palette.cyan)}"
        )
    else:
        print(f"{palette.wrap('Shunt voltage', palette.bold):<18}: {palette.wrap('n/a', palette.dim)}")

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

    if readings.current_ma is not None:
        flow = flow_labels.get(readings.flow, "Current unavailable")
        current_value = abs(readings.current_ma)
        flow_colour = flow_colours.get(readings.flow, palette.dim)
        current_str = f"{current_value:>8.2f} mA"
        print(
            f"{palette.wrap('Current', palette.bold):<18}: "
            f"{palette.wrap(current_str, palette.green)} "
            f"({palette.wrap(flow, flow_colour)})"
        )
    else:
        print(
            f"{palette.wrap('Current', palette.bold):<18}: "
            f"{palette.wrap('n/a', palette.dim)} {palette.wrap('(set shunt value)', palette.dim)}"
        )

    if readings.power_mw is not None and readings.current_ma is not None:
        direction = "to load" if readings.flow == "discharging" else "into battery" if readings.flow == "charging" else "minimal flow"
        power_w = abs(readings.power_mw) / 1000.0
        direction_colour = flow_colours.get(readings.flow, palette.dim)
        print(
            f"{palette.wrap('Power', palette.bold):<18}: "
            f"{palette.wrap(f'{power_w:>8.3f} W', palette.magenta)} "
            f"({palette.wrap(direction, direction_colour)})"
        )
    elif readings.power_mw is not None:
        power_w = readings.power_mw / 1000.0
        print(
            f"{palette.wrap('Power', palette.bold):<18}: "
            f"{palette.wrap(f'{power_w:>8.3f} W', palette.magenta)}"
        )
    else:
        print(f"{palette.wrap('Power', palette.bold):<18}: {palette.wrap('n/a', palette.dim)}")

    print(separator)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
