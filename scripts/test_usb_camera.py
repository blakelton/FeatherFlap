#!/usr/bin/env python3
"""Manual check for a USB camera using OpenCV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _paths import add_project_src_to_path

add_project_src_to_path()

from featherflap.config import DEFAULT_CAMERA_DEVICE_INDEX, get_settings
from featherflap.hardware.camera import (
    CameraUnavailable,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_FRAME_WIDTH,
    DEFAULT_JPEG_QUALITY,
    capture_jpeg_frame,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture a single JPEG frame from the USB camera using OpenCV. "
            "Useful for validating focus and verifying device numbering."
        )
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Camera device index or /dev path (defaults to FEATHERFLAP_CAMERA_DEVICE or 0).",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="Frame width to request (defaults to the project configuration).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=None,
        help="Frame height to request (defaults to the project configuration).",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=None,
        help="JPEG quality (10-95). Defaults to the project configuration.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to save the captured frame. If omitted, only metadata prints to stdout.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    device = (
        args.device
        if args.device is not None
        else settings.camera_device
        if settings.camera_device is not None
        else DEFAULT_CAMERA_DEVICE_INDEX
    )
    width = args.width if args.width is not None else getattr(settings, "camera_width", DEFAULT_FRAME_WIDTH)
    height = args.height if args.height is not None else getattr(settings, "camera_height", DEFAULT_FRAME_HEIGHT)
    quality = args.quality if args.quality is not None else getattr(settings, "camera_quality", DEFAULT_JPEG_QUALITY)

    try:
        payload = capture_jpeg_frame(device=device, width=width, height=height, quality=quality)
    except CameraUnavailable as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"ERROR: Unexpected failure capturing frame: {exc}", file=sys.stderr)
        return 1

    print(f"Captured {len(payload)} bytes from device {device}.")
    if args.output:
        try:
            args.output.write_bytes(payload)
        except OSError as exc:
            print(f"ERROR: Failed to write output file {args.output}: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote JPEG frame to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
