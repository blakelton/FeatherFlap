#!/usr/bin/env python3
"""Manual check for the CSI camera using Picamera2."""

from __future__ import annotations

import argparse
import sys
import time


def parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(
        description=(
            "Initialise Picamera2, start a preview capture, and shut it down to verify CSI camera wiring."
        )
    )
    parser.add_argument(
        "--preview-seconds",
        type=float,
        default=1.0,
        help="How long to run the camera preview before shutting down (default: 1 second).",
    )
    return parser, parser.parse_args()


def main() -> int:
    try:
        from picamera2 import Picamera2  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        print("ERROR: Picamera2 is not installed. Install python3-picamera2 on Raspberry Pi OS.", file=sys.stderr)
        return 2

    _parser, args = parse_args()
    duration = max(0.0, args.preview_seconds)

    camera: Picamera2
    try:
        camera = Picamera2()
    except Exception as exc:
        print(f"ERROR: Failed to initialise Picamera2: {exc}", file=sys.stderr)
        return 1

    try:
        camera.configure(camera.create_still_configuration())
        camera.start()
        print(f"Picamera2 started successfully; running preview for {duration} seconds...")
        time.sleep(duration)
        camera.stop()
        print("Picamera2 shut down cleanly.")
    except Exception as exc:
        print(f"ERROR: Picamera2 capture failed: {exc}", file=sys.stderr)
        return 1
    finally:
        camera.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
