# FeatherFlap Smart Bird House

FeatherFlap is a smart bird house platform designed for the Raspberry Pi Zero 2 W. The system combines resilient power management, environmental sensing, and imaging to monitor bird behaviour safely and reliably. The reference build now uses an AHT20 + BMP280 combo module for temperature, humidity, and barometric pressure. This repository includes a Python diagnostics server that exposes hardware tests through a browser so you can validate each peripheral after wiring.

## Quick Start (Raspberry Pi Zero 2 W)

1. Update apt and install required system packages:
   ```bash
   sudo apt update
   sudo apt install -y python3-pip python3-dev python3-opencv libatlas-base-dev \
       libjpeg-dev libopenjp2-7 libtiff6 libcamera-dev libcap-dev python3-libcamera \
       libavformat-dev libavcodec-dev libavdevice-dev libavutil-dev libavfilter-dev \
       libswscale-dev libswresample-dev
   ```
   These headers and libraries are needed by OpenCV, PiCamera2 (via `python-prctl`), and the `av` dependency used by the camera stack.
   _Expected time on Pi Zero 2 W: 5–10 minutes, depending on network speed._
2. Clone the repository and set up a virtual environment:
   ```bash
   git clone https://github.com/blakelton/FeatherFlap.git
   cd FeatherFlap
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   ```
   _Expected time: 2–4 minutes (dominated by the `pip` self-upgrade)._
3. Install native camera/video bindings from Raspberry Pi OS packages, then install Python dependencies. This avoids compiling large wheels (`opencv-python`, `av`) on the Pi.
   ```bash
   sudo apt install -y libopenblas-dev python3-opencv python3-av python3-picamera2 \
       python3-rpi.gpio python3-smbus
   pip install -e .
   ```
   _Expected time: 5–10 minutes for apt packages, <5 minutes for `pip install -e .`._
4. Run the diagnostics server:
   ```bash
   featherflap serve --host 0.0.0.0 --port 8000
   ```
   Open `http://<pi-ip>:8000/` to access the dashboard or call the JSON endpoints under `/api/tests`.
   _Expected time: server starts within 5–10 seconds once dependencies are installed._

---

## Application Overview

- `src/featherflap/` – Python package with hardware test abstractions and a FastAPI-powered diagnostics server.
- `tests/` – Unit tests ensuring the web application boots and routes are registered.
- `test_files/` – Original standalone scripts kept for reference and manual experimentation.
- `pyproject.toml` – Project metadata and dependencies (install with the optional `hardware` extra on the Raspberry Pi).

The diagnostics server provides:

- A web dashboard at `/` with buttons to run individual hardware checks or the full suite.
- JSON endpoints under `/api/tests` so the hardware verification workflow can be automated or integrated into other tools.
- Graceful fallbacks when optional libraries (e.g. `picamera2`, `RPi.GPIO`) are not installed or hardware is disconnected.
- Real-time sensor snapshots at `/api/status/environment` (AHT20 + BMP280) and `/api/status/ups` (PiZ-UpTime telemetry).
- USB camera capture endpoints at `/api/camera/frame` (single JPEG) and `/api/camera/stream` (MJPEG preview) for quick visual checks.

---

## Getting Started

### Prerequisites

- Python 3.10 or newer (3.11 recommended on Raspberry Pi OS Bookworm).
- A virtual environment tool (`python -m venv` comes bundled with CPython).
- On the Raspberry Pi, install system packages that the optional hardware libraries rely on:
  ```bash
  sudo apt update
  sudo apt install -y python3-pip python3-dev python3-opencv libatlas-base-dev \
      libjpeg-dev libopenjp2-7 libtiff5 libcamera-dev
  ```
  Enable I²C, camera, and other interfaces with `sudo raspi-config` as required by your build.

### Create a virtual environment

```bash
cd /home/azuelab/projects/FeatherFlap
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### Install dependencies

For local development without hardware:

```bash
pip install -e .
```

On the Raspberry Pi with peripherals connected, install the optional hardware extras:

```bash
pip install -e .[hardware]
```

### Run the diagnostics server

```bash
featherflap serve --host 0.0.0.0 --port 8000
```

The command above launches Uvicorn via the packaged CLI. By default it reads environment variables prefixed with `FEATHERFLAP_`. Common overrides:

- `FEATHERFLAP_HOST`, `FEATHERFLAP_PORT` – network binding.
- `FEATHERFLAP_ALLOWED_ORIGINS` – JSON list for CORS configuration.
- `FEATHERFLAP_I2C_BUS_ID` – Raspberry Pi I²C bus (default `1`).
- `FEATHERFLAP_UPTIME_I2C_ADDRESSES` – JSON list of PiZ-UpTime addresses to probe (defaults to `[72, 73, 75]`, i.e. 0x48/0x49/0x4B).
- `FEATHERFLAP_AHT20_I2C_ADDRESS` – AHT20 humidity/temperature sensor address (default `0x38`).
- `FEATHERFLAP_BMP280_I2C_ADDRESS` – BMP280 barometric pressure sensor address (default `0x76`).
- `FEATHERFLAP_PIR_PINS` and `FEATHERFLAP_RGB_LED_PINS` – BCM pin configuration for motion sensors and the RGB LED.
- `FEATHERFLAP_LOG_ERROR_ENABLED`, `FEATHERFLAP_LOG_WARNING_ENABLED`, `FEATHERFLAP_LOG_INFO_ENABLED`, `FEATHERFLAP_LOG_DEBUG_ENABLED` – toggle individual logging categories (errors, warnings, information, debug). Errors, warnings, and information logs are enabled by default; debug logs are opt-in.

Logs are emitted through a central `featherflap` logger and written to standard error with timestamps. Enable or disable each category independently by setting the flags above to `true`/`false`. For example, `FEATHERFLAP_LOG_DEBUG_ENABLED=true` surfaces fine-grained diagnostic messages without altering the other categories.

### Logging

FeatherFlap initialises a single namespaced logger (`featherflap`) that all components share:

- The CLI and FastAPI factory configure the logger automatically, so running `featherflap serve` immediately produces timestamped logs on stderr.
- Change verbosity at runtime through the `FEATHERFLAP_LOG_*_ENABLED` flags. Set a flag to `false` to suppress that level or `true` to enable it; errors, warnings, and informational messages default to `true`, while debug starts disabled.
- Debug mode (`FEATHERFLAP_LOG_DEBUG_ENABLED=true`) reveals granular traces for I²C access, camera streaming, and test execution. This is ideal for troubleshooting but can emit a lot of output—especially when MJPEG streaming runs continuously—so leave it off unless needed.
- When embedding the diagnostics stack elsewhere, call `featherflap.logger.get_logger("your.module")` to obtain a scoped child logger and stay inside the unified logging tree.

Visit `http://<raspberry-pi-ip>:8000/` in a browser on the same network to access the dashboard. Each test streams its results back to the page and displays structured diagnostics.

Useful API routes once the server is running:

- `GET /api/status/environment` — current readings from the AHT20 + BMP280 combo board.
- `GET /api/status/ups` — live telemetry from the PiZ-UpTime HAT (voltages and board temperature).
- `GET /api/camera/frame` — capture a single JPEG frame from the configured USB camera.
- `GET /api/camera/stream` — MJPEG stream suitable for browser previews when validating focus/FOV.

### Command-line alternatives

You can also start the server with Uvicorn directly:

```bash
uvicorn featherflap.server.app:create_application --factory --host 0.0.0.0 --port 8000
```

### Run automated tests

```bash
python -m pytest
```

If optional hardware dependencies are missing locally, the diagnostics gracefully mark the corresponding tests as `skipped`. Run the suite on a development machine to ensure the FastAPI app builds, and on the Raspberry Pi to validate the full stack.

### Manual hardware validation scripts

The repo now ships standalone scripts that exercise each peripheral without bringing up the FastAPI server. Activate your virtual environment first, then run:

```bash
python scripts/test_i2c_bus.py                # Verify the I2C device node is reachable
python scripts/test_ups.py --addresses 0x48   # Check PiZ-UpTime telemetry on specific addresses
python scripts/test_environmental.py          # Read AHT20 + BMP280 values once
python scripts/test_picamera.py               # Spin up the CSI camera via Picamera2
python scripts/test_usb_camera.py --output frame.jpg  # Capture a JPEG from the USB camera
python scripts/test_pir.py --samples 5        # Poll PIR sensor pins multiple times
python scripts/test_rgb_led.py --rounds 3     # Cycle the RGB LED channels several times
```

Each script honours the `FEATHERFLAP_*` configuration variables and exposes CLI flags so you can override bus numbers, GPIO pins, or camera options per run.

---

## Hardware Overview & Purpose

The Smart Bird House project aims to create a robust, autonomous bird‑monitoring system that can:

- Observe and record bird activity (e.g. via motion detection, camera capture)
- Measure environmental data (temperature, humidity, light, etc.)
- Operate reliably through power outages or remote installations (solar backup + UPS)
- Provide telemetry / logs and safe shutdown when battery is low
- Be modular and maintainable, so components can be added or swapped

In effect, the system is intended to live inside (or adjacent to) a birdhouse, monitoring bird behavior while being power resilient and remote-capable.

---

## Hardware Bill of Materials (BOM)

| # | Component / Module | Description & Role | Communication / Interface | Notes / Considerations |
|---|---------------------|----------------------|-----------------------------|---------------------------|
| 1 | Raspberry Pi Zero (or Zero W) | The main compute and control unit | Runs Linux, connects to all sensors/peripherals | Ensure it has WiFi (if required) or network connectivity |
| 2 | Camera module (NoIR / IR sensitive) | Captures stills / video inside the birdhouse | CSI camera interface | Use NoIR version if you want IR sensitivity; plan lens / focus for small interior |
| 3 | Compact UPS HAT with solar input (Seengreat Pi Zero UPS HAT (B)) | Provides battery backup, solar charging, and power path switching | Powers Pi 5V; monitoring via I²C (INA219, gauge chip) | Accepts USB and solar input (5–24 V) |
| 4 | Li‑Ion / Li‑Polymer battery (3.7 V single cell) | Energy storage for backup / off-grid | Electrically integrated in the UPS HAT | Choose capacity based on expected load and runtime |
| 5 | Solar panel (5–24 V) | Harvests solar energy to charge battery and sustain system | Wired to UPS solar input terminal | Select panel size (W, Vmp) appropriate for your locale |
| 6 | AHT20 + BMP280 combo sensor | Read ambient temperature, humidity, and barometric pressure | I²C (0x38 + 0x76/0x77) | Mount away from drafts; provide airflow without disturbing the nest |
| 7 | Light sensor (e.g. photodiode, LDR, TSL2561) | Measure ambient light / darkness | Analog (via ADC) or I²C | Use to trigger camera or manage IR lighting |
| 8 | Motion sensor (PIR) | Detect bird arrival / activity | Digital GPIO (binary high/low) | Use debounce / filtering in software to avoid false triggers |
| 9 | Optional IR LED or illumination | Provide illumination (in IR) when it's dark, for the camera | Controlled via GPIO / transistor | Use current-limiting resistor; avoid disturbing the birds |
| 10 | Optional environmental sensors (e.g. air pressure, sound, CO₂) | Additional data capture | I²C, SPI, or analog | Include only what you need to avoid overcomplexity |
| 11 | Wiring, connectors, standoffs, screws, enclosure, protective coatings | Mechanical / electrical support | – | Weatherproofing is critical; consider cable glands, sealants |

---

## Pinout & Connections to Raspberry Pi

| UPS / Sensor / Function | Pi Header Pin | Signal / Purpose | Notes |
|--------------------------|----------------|---------------------|-------|
| UPS 5 V Output | Pin 2 (5V) | +5V power supply to Pi | Primary power line |
| UPS 5 V Output | Pin 4 (5V) | +5V also tied to header redundant | Good practice to power from both 5V pins if available |
| UPS Ground | Pin 6 (GND) | Return ground reference | Connect to ground bus |
| UPS I²C SDA | Pin 3 (SDA / GPIO2) | UPS monitoring data (voltage, current) | Use same bus for other I²C sensors |
| UPS I²C SCL | Pin 5 (SCL / GPIO3) | UPS monitoring clock | Shared with other I²C devices |
| Temp/Humidity Sensor (I²C) | Pin 3 (SDA) | Data line | Shared I²C bus |
| Temp/Humidity Sensor (I²C) | Pin 5 (SCL) | Clock line | Shared |
| Light Sensor (if I²C) | Pin 3, Pin 5 | Shared bus | Or analog to ADC if non-digital |
| Motion Sensor (PIR) | GPIO pin (e.g. Pin 11 / GPIO17) | Digital input | Use a free GPIO that supports interrupts |
| IR LED / Illumination | GPIO pin (e.g. Pin 13 / GPIO27) | Digital output (or via transistor) | Provide ground and control path |
| Optional additional sensors | Various GPIO / SPI / I²C | As required | Use multiplexing or expanders if needed |

---

## Wiring & Integration Steps

1. Turn OFF UPS output via the slide switch (so Pi is not powered during wiring).
2. Mount the UPS HAT flush on the Pi Zero’s 40‑pin header; secure with M2.5 standoffs/screws.
3. Connect battery to UPS battery socket (observe correct polarity).
4. Attach solar panel (if used) to the UPS solar input terminal block (observe polarity).
5. Wire sensors to the I²C or GPIO pins as described.
6. Enable UPS output by sliding its switch ON.
7. Power up the Pi and verify it boots.
8. Test I²C communication (via `i2cdetect`).
9. Test sensor readings via scripts.
10. Simulate power outage and verify the UPS maintains operation.
11. Verify safe shutdown when battery is low.
12. Restore power and confirm normal operation.

---

## Software & Monitoring

Your software should poll I²C sensors and UPS data, log readings, and initiate safe shutdowns.

### Example (Python pseudocode)

```python
import smbus2, time

def read_ups_metrics():
    # Read voltage, current, etc. via INA219
    pass

def read_environment():
    # Temperature, humidity, light sensors
    pass

def safe_shutdown():
    # Trigger system shutdown
    pass

while True:
    volt, curr, pct = read_ups_metrics()
    temp, hum, light = read_environment()
    print(f"UPS: {volt:.2f}V {curr:.2f}A {pct}% | Env: {temp}C {hum}% L={light}")
    if pct < 10 or volt < 3.0:
        safe_shutdown()
    time.sleep(10)
```

---

## Best Practices & Design Notes

- **Battery & Solar Sizing:** Choose capacity and panel wattage for your sunlight conditions.
- **Protection:** Fuse solar lines, ensure correct polarity.
- **Thermal:** Allow ventilation; UPS circuits generate heat.
- **Weatherproofing:** Enclose electronics, use desiccant and glands.
- **I²C Bus:** Keep short, ensure proper pull‑ups.
- **Safe Shutdown:** Calibrate thresholds carefully.
- **Battery Maintenance:** Replace aged batteries periodically.

---

## Summary

The Smart Bird House integrates environmental sensing, video capture, and power resilience in one platform, built around a Raspberry Pi Zero and a solar‑UPS module. It enables autonomous wildlife monitoring with reliable operation and safe power management.

### Legacy scripts

The historical one-off scripts remain in `test_files/` for reference, but all day-to-day functionality now ships through the packaged `featherflap` application and its test suite.
