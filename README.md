# FeatherFlap Smart Bird House

FeatherFlap is a smart bird house platform designed for the Raspberry Pi Zero 2 W. The system combines resilient power management, environmental sensing, and imaging to monitor bird behaviour safely and reliably. The reference build now uses an AHT20 + BMP280 combo module for temperature, humidity, and barometric pressure. This repository includes a Python diagnostics server that exposes hardware tests through a browser so you can validate each peripheral after wiring.

## Intended Use & Deployment Flow

FeatherFlap is meant to accompany the full lifecycle of a smart bird-house installation—from bench assembly to outdoor deployment and ongoing maintenance. The typical journey looks like this:

- **Bench bring-up:** Assemble the Pi, Seengreat UPS HAT, sensors, and cameras. Use the CLI scripts (`scripts/`) to verify each peripheral before you enclose the hardware.
- **Configuration & burn-in:** Set `FEATHERFLAP_*` environment variables or an `.env` file to match your wiring (GPIO pins, I²C addresses, UPS shunt value). Run `featherflap serve` locally to exercise the diagnostics repeatedly while monitoring logs.
- **Deployment:** Move the Pi into the bird house, power it via the UPS, and keep the diagnostics API running in the background. The dashboard at `/` offers a quick health checklist during installation.
- **Remote checks:** Periodically tunnel into the device (SSH + port-forwarding) to run the automated suite (`pytest`) or trigger `/api/tests/run-all` so you can confirm uptime, camera availability, and sensor drift without disassembling the hardware.
- **Maintenance:** When swapping sensors, updating firmware, or replacing batteries, revisit the scripts and diagnostics to ensure each component recovers correctly.

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

## Project Structure

| Path | Purpose |
| --- | --- |
| `src/featherflap/` | Source package containing all runtime code. See the subfolders below. |
| `src/featherflap/hardware/` | Diagnostics framework: hardware abstractions (`base.py`), registry, Seengreat UPS/INA219 driver (`power.py`), environmental sensor drivers (`sensors.py`), USB/CSI camera helpers, and the concrete test implementations (`tests.py`). |
| `src/featherflap/server/` | FastAPI application factory, REST routes, and Typer CLI glue that launches Uvicorn. |
| `src/featherflap/config.py` | Pydantic settings model sourcing values from `FEATHERFLAP_*` environment variables or an `.env` file. |
| `src/featherflap/logger.py` | Central logging configuration with runtime toggles for error/warning/info/debug streams. |
| `scripts/` | Command-line utilities that probe individual peripherals (UPS, I²C bus, sensors, cameras, PIR, RGB LED). Useful for bench diagnostics without running the web stack. |
| `test_files/` | Legacy one-off experiments retained for reference (older prototypes, oscilloscope captures, etc.). Not part of the active toolchain but occasionally helpful during hardware debugging. |
| `tests/` | Pytest suite covering application boot, dependency guards, and configuration parsing. Read `tests/README.md` for execution tips. |
| `pyproject.toml` | Project metadata, dependencies, entry points (`featherflap` CLI), and the optional `[project.optional-dependencies.hardware]` extras set for Raspberry Pi deployments. |
| `README.md`, `AGENTS.md` | End-user and automation-agent documentation respectively. |

### Runtime Overview

Once installed, the diagnostics server provides:

- A browser dashboard (`GET /`) to orchestrate individual tests or run the full suite.
- JSON metadata (`GET /api/tests`) suitable for external monitoring or CI pipelines.
- Per-test execution (`POST /api/tests/{id}`) and bulk execution (`POST /api/tests/run-all`) endpoints.
- Near-real-time status feeds for sensors and power systems:
  - `/api/status/environment` – temperature, humidity, and pressure snapshots from the AHT20 + BMP280 combo board.
  - `/api/status/ups` – INA219 bus voltage, shunt drop, computed current, and power from the Seengreat UPS.
- USB camera helpers: `/api/camera/frame` for a single JPEG capture and `/api/camera/stream` for MJPEG previewing.

Every route degrades gracefully when optional dependencies are absent (for example if `picamera2` is not installed on a development machine) and reports `SKIPPED` rather than failing outright.

### Operating Modes

FeatherFlap now supports **two mutually-exclusive modes**:

- **Test mode (`mode=test`, default):** the server prioritises diagnostics. All hardware tests are available and multiple camera operations can run concurrently. This is the mode to use during bench validation or troubleshooting.
- **Run mode (`mode=run`):** the system pivots to production behaviour. Motion-triggered recording, sleep scheduling, and live camera streaming coexist, but diagnostics that require camera access are limited. Run and test modes cannot run simultaneously—the CLI enforces this by acquiring a mode lock.

Switch modes via configuration (`FEATHERFLAP_MODE`) or the CLI:

```bash
# Start the server directly in run mode
featherflap serve --mode run

# Revert to diagnostics mode
featherflap serve --mode test
```

If a process is already running in the opposite mode you will receive a descriptive error; stop the other instance before switching.

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

If you plan to run the automated test suite, install pytest (it isn’t bundled with the editable install):

```bash
pip install pytest
```

### Run the diagnostics server

```bash
featherflap serve --host 0.0.0.0 --port 8000
```

The command above launches Uvicorn via the packaged CLI. By default it reads environment variables prefixed with `FEATHERFLAP_`. Common overrides:

- `FEATHERFLAP_HOST`, `FEATHERFLAP_PORT` – network binding.
- `FEATHERFLAP_ALLOWED_ORIGINS` – JSON list for CORS configuration.
- `FEATHERFLAP_I2C_BUS_ID` – Raspberry Pi I²C bus (default `1`).
- `FEATHERFLAP_UPTIME_I2C_ADDRESSES` – JSON list of UPS telemetry addresses (defaults to `[64]`, i.e. `0x40` for the Seengreat INA219).
- `FEATHERFLAP_UPTIME_SHUNT_RESISTANCE_OHMS` – shunt resistor value used to derive current from the INA219 (default `0.01` Ω).
- `FEATHERFLAP_AHT20_I2C_ADDRESS` – AHT20 humidity/temperature sensor address (default `0x38`).
- `FEATHERFLAP_BMP280_I2C_ADDRESS` – BMP280 barometric pressure sensor address (default `0x76`).
- `FEATHERFLAP_PIR_PINS` and `FEATHERFLAP_RGB_LED_PINS` – BCM pin configuration for motion sensors and the RGB LED.
- `FEATHERFLAP_LOG_ERROR_ENABLED`, `FEATHERFLAP_LOG_WARNING_ENABLED`, `FEATHERFLAP_LOG_INFO_ENABLED`, `FEATHERFLAP_LOG_DEBUG_ENABLED` – toggle individual logging categories (errors, warnings, information, debug). Errors, warnings, and information logs are enabled by default; debug logs are opt-in.

Logs are emitted through a central `featherflap` logger and written to standard error with timestamps. Enable or disable each category independently by setting the flags above to `true`/`false`. For example, `FEATHERFLAP_LOG_DEBUG_ENABLED=true` surfaces fine-grained diagnostic messages without altering the other categories.

### Configuration reference

| Variable | Default | Description |
| --- | --- | --- |
| `FEATHERFLAP_HOST` / `FEATHERFLAP_PORT` | `0.0.0.0` / `8000` | Bind address and port for the FastAPI diagnostics server. |
| `FEATHERFLAP_ALLOWED_ORIGINS` | `[*]` | JSON list of origins allowed to access the API (CORS). |
| `FEATHERFLAP_I2C_BUS_ID` | `1` | Raspberry Pi I²C bus used for sensors and the UPS. |
| `FEATHERFLAP_UPTIME_I2C_ADDRESSES` | `[64]` (`0x40`) | INA219 telemetry addresses. Add more if your board exposes extra devices. |
| `FEATHERFLAP_UPTIME_SHUNT_RESISTANCE_OHMS` | `0.01` | Shunt resistor value (Ω) used to compute current/power from the INA219 readings. |
| `FEATHERFLAP_AHT20_I2C_ADDRESS` / `FEATHERFLAP_BMP280_I2C_ADDRESS` | `0x38` / `0x76` | Addresses for the environmental sensor combo board. |
| `FEATHERFLAP_CAMERA_DEVICE` | `0` | Default V4L2 device index for USB camera diagnostics. Set to `null` to skip. |
| `FEATHERFLAP_PIR_PINS` | `[17, 27]` | PIR motion sensor GPIO pins (BCM numbering). Accepts comma/space-separated strings or JSON. |
| `FEATHERFLAP_RGB_LED_PINS` | `(24, 23, 18)` | RGB LED GPIO triplet in the order (red, green, blue). |
| `FEATHERFLAP_LOG_*_ENABLED` | errors/warnings/info=`true`, debug=`false` | Fine-grained logging toggles controlling which severities are emitted. |

You can supply these values via exported environment variables, a `.env` file placed in the project root, or direct Pydantic overrides when instantiating `AppSettings` in custom tooling.

### Logging

FeatherFlap initialises a single namespaced logger (`featherflap`) that all components share:

- The CLI and FastAPI factory configure the logger automatically, so running `featherflap serve` immediately produces timestamped logs on stderr.
- Change verbosity at runtime through the `FEATHERFLAP_LOG_*_ENABLED` flags. Set a flag to `false` to suppress that level or `true` to enable it; errors, warnings, and informational messages default to `true`, while debug starts disabled.
- Debug mode (`FEATHERFLAP_LOG_DEBUG_ENABLED=true`) reveals granular traces for I²C access, camera streaming, and test execution. This is ideal for troubleshooting but can emit a lot of output—especially when MJPEG streaming runs continuously—so leave it off unless needed.
- When embedding the diagnostics stack elsewhere, call `featherflap.logger.get_logger("your.module")` to obtain a scoped child logger and stay inside the unified logging tree.

Visit `http://<raspberry-pi-ip>:8000/` in a browser on the same network to access the dashboard. Each test streams its results back to the page and displays structured diagnostics.

Useful API routes once the server is running:

- `GET /api/status/environment` — current readings from the AHT20 + BMP280 combo board.
- `GET /api/status/ups` — live telemetry from the Seengreat Pi Zero UPS HAT (B), exposing INA219-derived bus voltage, shunt drop, and computed current/power.
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

If optional hardware dependencies are missing locally, the diagnostics gracefully mark the corresponding tests as `skipped`. Run the suite on a development machine to ensure the FastAPI app builds, and on the Raspberry Pi to validate the full stack. See [tests/README.md](tests/README.md) for a breakdown of what each test covers.

Need more detailed output? Add `-vv -r a` to list every test and its result:

```bash
python -m pytest -vv -r a
```

### Manual hardware validation scripts

The repo now ships standalone scripts that exercise each peripheral without bringing up the FastAPI server. Activate your virtual environment first, make sure I2C is enabled (`sudo raspi-config nonint do_i2c 0` or add `dtparam=i2c_arm=on` to `/boot/firmware/config.txt` on Raspberry Pi OS Bookworm, then reboot), then run:

```bash
python scripts/test_i2c_bus.py                # Verify the I2C device node is reachable
python scripts/test_ups.py --addresses 0x40 --shunt-ohms 0.01   # Check Seengreat UPS telemetry (override if addresses/ohms differ)
python scripts/test_environmental.py          # Read AHT20 + BMP280 values once
python scripts/test_picamera.py               # Spin up the CSI camera via Picamera2
python scripts/test_usb_camera.py --output frame.jpg  # Capture a JPEG from the USB camera
python scripts/test_pir.py --samples 5        # Poll PIR sensor pins multiple times
python scripts/test_rgb_led.py --rounds 3     # Cycle the RGB LED channels several times
```

Each script honours the `FEATHERFLAP_*` configuration variables and exposes CLI flags so you can override bus numbers, GPIO pins, or camera options per run.
For the UPS module specifically, supply the INA219/HM1160 addresses (`FEATHERFLAP_UPTIME_I2C_ADDRESSES` or `--addresses`) that you discovered with `i2cdetect` so telemetry comes from the Seengreat board.
Refer to [scripts/README.md](scripts/README.md) for a script-by-script feature table and additional usage tips.

> **Note**  
> The I2C-dependent scripts (`test_environmental.py`, `test_ups.py`, `test_i2c_bus.py`) require the system I2C interface (`dtparam=i2c_arm=on` in `/boot/firmware/config.txt`, or enable it via `sudo raspi-config`) plus either `python3-smbus` from apt or the `smbus2` wheel. If you see “smbus/smbus2 library is not installed”, install the package with `sudo apt install python3-smbus` (or `pip install smbus2` inside your virtualenv).

---

## Integrating the Diagnostics in Your Workflow

There are several ways to consume the diagnostics once the hardware is deployed:

- **Browser-based health checks:** Point a desktop or mobile browser at `http://<pi>:8000/` while standing near the bird house. Kick off `Run full suite` and watch results stream in within a few seconds.
- **Command-line automation:** Use `curl` or `httpie` from an SSH session to hit `/api/tests/run-all` and parse the JSON for alerting. The overall status is derived from the highest-severity result (`error` > `warning` > `skipped` > `ok`).
- **Python embedding:** Import `featherflap.hardware` in your own scripts to run selected diagnostics. Example: `from featherflap.hardware.tests import SeengreatUPSTest; result = SeengreatUPSTest().run()`.
- **CI regression tests:** On development machines without hardware, run `pytest -vv -r a`. Hardware-dependent tests mark themselves as `SKIPPED`, so your continuous integration job still produces a green build while reminding reviewers which components were absent.
- **Scheduled watchdogs:** Combine `cron` with the CLI scripts (`scripts/test_*.py`) or the REST API to log UPS metrics periodically, then ingest the data into your observability stack.

The project is intentionally lightweight—no database or background workers—so you can embed it alongside other services on the Pi or wrap it in systemd/pm2 containers as needed.

---

## Run Mode Behaviour

When `FEATHERFLAP_MODE=run` (or `featherflap serve --mode run`), the server augments its diagnostics with production automation:

- **Motion-triggered recording:** PIR sensors are polled every `FEATHERFLAP_MOTION_POLL_INTERVAL_SECONDS`. A trigger reserves the camera, captures up to `FEATHERFLAP_RECORDING_MAX_SECONDS` of video using the configured resolution (`FEATHERFLAP_CAMERA_RECORD_WIDTH` × `FEATHERFLAP_CAMERA_RECORD_HEIGHT`) and frame rate, and stores the clip under `FEATHERFLAP_RECORDINGS_PATH` in date-based folders. Finished files are optionally mirrored to `FEATHERFLAP_NETWORK_EXPORT_PATH` for off-device archival.
- **Camera serialization:** A dedicated coordinator prevents simultaneous camera operations. Live streaming and still captures return HTTP 423 (Locked) while a recording is running, fulfilling the “only one feed at a time” requirement.
- **Sleep windows:** Provide `FEATHERFLAP_SLEEP_WINDOWS` (e.g. `["22:00-06:00", "13:00-14:00"]`) to suspend motion polling during quiet hours and conserve power. The controller automatically resumes afterwards.
- **Status visibility:** Query `GET /api/run/status` to inspect whether a recording is active, which component currently holds the camera lock, and when the last capture finished.

Diagnostics continue to operate in run mode—non-conflicting tests remain available—while camera-centric diagnostics are hidden to keep the recording pipeline stable.

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

### Seengreat Pi Zero UPS HAT (B) Highlights

- **Smart power-path management:** TPS61088 + ETA6003 combo provides seamless switchover between external supply, Li-ion cell, and boosted 5 V output so the Pi never browns out.
- **Solar-ready charging:** CN3791 MPPT controller accepts 5 V–24 V photovoltaic input for efficient solar harvesting—match the panel voltage/current to your locale and battery size.
- **Real-time telemetry:** The onboard INA219 monitor exposes bus voltage and current draw over I²C. Expect to see it at `0x40`; some revisions also surface a secondary HM1160 fuel gauge—probe with `sudo i2cdetect -y 1` if you plan to integrate it.
- **Field diagnostics:** Onboard LED fuel gauge mirrors the telemetry so you can quickly check the charge level even when the Pi is offline.
- **Battery safeguards:** Integrated protection IC manages safe charge/discharge envelopes—still observe the recommended cell capacity and temperature range from Seengreat’s documentation.

Update the `FEATHERFLAP_UPTIME_I2C_ADDRESSES` setting (and `FEATHERFLAP_UPTIME_SHUNT_RESISTANCE_OHMS` if your board uses a different shunt) so the diagnostics poll and scale telemetry correctly.

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
| RGB LED (R/G/B) | Pins 18/16/12 (GPIO24/23/18) | LED channels (red/green/blue) | Drive via GPIO with current-limiting resistors |
| IR LED / Illumination | GPIO pin (e.g. Pin 19 / GPIO10) | Digital output (or via transistor) | Optional IR flood or lighting |
| Optional additional sensors | Various GPIO / SPI / I²C | As required | Use multiplexing or expanders if needed |

---

### Raspberry Pi 40‑pin Header Cheat Sheet

```text
┌───────────────────────────────────────────────────────────────┐
│ 3V3 (1)  [●]   (2)  5V  [●][UPS 5V OUT]                      │
│ SDA1 / GPIO2 (3)  [●][UPS I2C SDA]   (4)  5V  [●][UPS 5V OUT]│
│ SCL1 / GPIO3 (5)  [●][UPS I2C SCL]   (6)  GND [●][UPS GND]   │
│ GPIO4         (7)  [○]              (8)  TXD0 / GPIO14 [○]    │
│ GND           (9)  [●]              (10) RXD0 / GPIO15 [○]    │
│ GPIO17 (PIR1) (11) [★]              (12) GPIO18 (LED‑B) [♦]   │
│ GPIO27 (PIR2) (13) [★]              (14) GND [●]               │
│ GPIO22        (15) [○]              (16) GPIO23 (LED‑G) [♦]   │
│ 3V3           (17) [●]              (18) GPIO24 (LED‑R) [♦]   │
│ MOSI / GPIO10 (19) [○]              (20) GND [●]               │
│ MISO / GPIO9  (21) [○]              (22) GPIO25 [○]            │
│ SCLK / GPIO11 (23) [○]              (24) CE0 / GPIO8 [○]       │
│ GND          (25) [●]               (26) CE1 / GPIO7 [○]       │
│ ID_SD / GPIO0 (27) [○]              (28) ID_SC / GPIO1 [○]     │
│ GPIO5        (29) [○]               (30) GND [●]               │
│ GPIO6        (31) [○]               (32) GPIO12 [○]            │
│ GPIO13       (33) [○]               (34) GND [●]               │
│ GPIO19       (35) [○]               (36) GPIO16 [○]            │
│ GPIO26       (37) [○]               (38) GPIO20 [○]            │
│ GND          (39) [●]               (40) GPIO21 [○]            │
└───────────────────────────────────────────────────────────────┘
Legend: [●] Power/GND · [★] PIR sensors · [♦] RGB LED (R,G,B) · [○] Spare GPIO · [UPS …] Seengreat UPS
```

---

## Wiring & Integration Steps

1. Turn OFF UPS output via the slide switch (so Pi is not powered during wiring).
2. Mount the UPS HAT flush on the Pi Zero’s 40‑pin header; secure with M2.5 standoffs/screws.
3. Connect battery to UPS battery socket (observe correct polarity).
4. Attach solar panel (if used) to the UPS solar input terminal block (observe polarity).
5. Wire sensors to the I²C or GPIO pins as described.
6. Enable UPS output by sliding its switch ON.
7. Power up the Pi and verify it boots.
8. Test I²C communication (via `sudo i2cdetect -y 1`) and confirm the UPS telemetry addresses (e.g. INA219 at `0x40`).
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
    metrics = read_ups_metrics()  # Expected keys: bus_voltage_v, current_ma, power_mw, ...
    volt = metrics["bus_voltage_v"]
    curr_a = (metrics.get("current_ma") or 0) / 1000.0
    temp, hum, light = read_environment()
    print(f"UPS: {volt:.2f}V {curr_a:.2f}A | Env: {temp}C {hum}% L={light}")
    if volt < 4.8:
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
