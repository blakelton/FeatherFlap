#!/usr/bin/env python3
"""Enable or disable USB (UVC) cameras for FeatherFlap.

This helper toggles the `authorized` sysfs switch for all detected USB webcams,
allowing you to power down the devices temporarily for power saving and restore
them later without rebooting. Root privileges are required when changing state.

Examples:

    # Show current USB webcam status
    python scripts/manage_usb_cameras.py --status

    # Disable all UVC webcams until re-enabled (requires sudo)
    sudo python scripts/manage_usb_cameras.py --disable

    # Re-enable previously disabled UVC webcams (requires sudo)
    sudo python scripts/manage_usb_cameras.py --enable
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from _paths import add_project_src_to_path

add_project_src_to_path()


def require_root() -> None:
    if os.geteuid() != 0:
        print("ERROR: This operation requires root privileges. Re-run with sudo.", file=sys.stderr)
        raise SystemExit(2)


def find_usb_camera_devices() -> List[str]:
    base = Path("/sys/bus/usb/drivers/uvcvideo")
    if not base.exists():
        return []
    devices: set[str] = set()
    for entry in base.iterdir():
        if entry.name in {"bind", "module", "new_id", "remove_id", "uevent"}:
            continue
        if ":" not in entry.name:
            continue
        devices.add(entry.name.split(":")[0])
    return sorted(devices)


def read_authorized(device_id: str) -> Optional[bool]:
    target = Path("/sys/bus/usb/devices") / device_id / "authorized"
    try:
        value = target.read_text().strip()
    except FileNotFoundError:
        return None
    return value == "1"


def set_authorized(device_id: str, enabled: bool) -> None:
    target = Path("/sys/bus/usb/devices") / device_id / "authorized"
    if not target.exists():
        raise FileNotFoundError(f"Authorized file not found for device {device_id} (path {target})")
    target.write_text("1\n" if enabled else "0\n")


def usb_status() -> int:
    devices = find_usb_camera_devices()
    if not devices:
        print("No USB UVC cameras detected.")
        return 0
    print("USB UVC camera devices:")
    for device in devices:
        state = read_authorized(device)
        label = "enabled" if state else "disabled" if state is not None else "unknown (missing authorized state)"
        print(f"  - {device}: {label}")
    return 0


def usb_toggle(enable: bool) -> int:
    require_root()
    devices = find_usb_camera_devices()
    if not devices:
        print("No USB UVC cameras detected.")
        return 0
    changed = 0
    desired = "enabled" if enable else "disabled"
    for device in devices:
        current = read_authorized(device)
        if current is None:
            print(f"Skipping {device}: unable to determine current state.", file=sys.stderr)
            continue
        if current == enable:
            print(f"{device} already {desired}.")
            continue
        try:
            set_authorized(device, enable)
        except OSError as exc:
            print(f"ERROR: Failed to set {device} {desired}: {exc}", file=sys.stderr)
            continue
        print(f"{device} {desired}.")
        changed += 1
    if changed == 0:
        print("No USB cameras changed state.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enable or disable USB (UVC) cameras for FeatherFlap.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--enable", action="store_true", help="Enable all detected USB UVC cameras.")
    group.add_argument("--disable", action="store_true", help="Disable all detected USB UVC cameras.")
    parser.add_argument("--status", action="store_true", help="Print USB camera status (default if no action).")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.enable:
        return usb_toggle(True)
    if args.disable:
        return usb_toggle(False)
    return usb_status()


if __name__ == "__main__":
    raise SystemExit(main())
