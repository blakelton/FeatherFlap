# FeatherFlap Test Suite

This directory contains the automated regression tests for the FeatherFlap diagnostics stack. The suite is intentionally light so it can run on both development machines and Raspberry Pi hardware.

## What's Covered

- `test_app.py` ensures the FastAPI application factory builds, registers core routes, and exposes the diagnostics dashboard.
- `test_dependencies.py` verifies optional hardware libraries are skipped gracefully when unavailable (mirrors on-device behaviour).
- `test_config_pir.py` exercises the configuration parsing for PIR GPIO inputs, covering single-pin and list overrides from environment variables.
- Hardware peripherals that require live devices (RGB LED, USB camera, Picamera2) are validated through the CLI helpers in [`scripts/`](../scripts/README.md) rather than automated pytest modules.

## Running the Tests

1. Activate your project virtual environment:
   ```bash
   source .venv/bin/activate
   ```
2. Install pytest if you haven't already:
   ```bash
   pip install pytest
   ```
3. Execute the suite from the repository root:
   ```bash
   python -m pytest
   ```

On Raspberry Pi hardware without optional dependencies (Picamera2, OpenCV, RPi.GPIO, etc.), affected checks are marked as `skipped` rather than failing. Run the tests locally to catch regressions quickly; run them on-device when validating the hardware paths.

## Getting More Detail from Pytest

- Append `-vv` for verbose function-level output, and `-r a` to see a summary of all outcomes (passed, skipped, xfailed, xpassed):
  ```bash
python -m pytest -vv -r a
```
- Combine with `--maxfail=1` if you want pytest to stop at the first failure while still reporting prior results:
  ```bash
  python -m pytest -vv -r a --maxfail=1
  ```

## Manual Hardware Exercises

Use the hardware scripts whenever you need to validate peripherals on an actual Raspberry Pi:

- `python scripts/test_i2c_bus.py --bus-id 1` – confirm the chosen I²C bus opens successfully.
- `python scripts/test_ups.py --addresses 0x40 0x0b` – read Seengreat UPS telemetry (adjust addresses as required).
- `python scripts/test_environmental.py --aht20-address 0x38 --bmp280-address 0x76` – capture one set of AHT20/BMP280 readings.
- `python scripts/test_pir.py --pins 17 27 --samples 5` – poll the configured PIR GPIO inputs multiple times.
- `python scripts/test_rgb_led.py --rounds 3` – pulse the RGB LED channels to confirm wiring and GPIO control.
- `python scripts/test_picamera.py --preview-seconds 3` – bring up Picamera2 and verify the CSI camera path.
- `python scripts/test_usb_camera.py --output frame.jpg` – capture a JPEG frame from a USB webcam via OpenCV.

Those helpers live outside the automated test suite so they can interact with real hardware safely; see [`scripts/README.md`](../scripts/README.md) for full options.
