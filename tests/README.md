# FeatherFlap Test Suite

This directory contains the automated regression tests for the FeatherFlap diagnostics stack. The suite is intentionally light so it can run on both development machines and Raspberry Pi hardware.

## What's Covered

- `test_app.py` ensures the FastAPI application factory builds, registers core routes, and exposes the diagnostics dashboard.
- `test_dependencies.py` verifies optional hardware libraries are skipped gracefully when unavailable (mirrors on-device behaviour).
- `test_config_pir.py` exercises the configuration parsing for PIR GPIO inputs, covering single-pin and list overrides from environment variables.

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
