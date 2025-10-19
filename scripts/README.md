# FeatherFlap Hardware Scripts

The `scripts/` folder hosts command-line helpers for validating each peripheral without launching the FastAPI diagnostics server. They are designed for quick, manual checks while wiring or debugging hardware on the Raspberry Pi.

## Common Usage Notes

- Activate your virtual environment first: `source .venv/bin/activate`
- Ensure I²C is enabled on the Pi (`sudo raspi-config nonint do_i2c 0` or `dtparam=i2c_arm=on` in `/boot/firmware/config.txt` followed by a reboot).
- Each script honours the `FEATHERFLAP_*` environment variables so you can adjust GPIO pins, I²C bus IDs, and addresses without editing code.

## Available Scripts

| Script | Purpose | Key Flags |
| ------ | ------- | --------- |
| `test_i2c_bus.py` | Confirm the I²C bus is available and responsive. | `--bus-id` to choose an alternate bus. |
| `test_ups.py` | Poll the Seengreat Pi Zero UPS HAT (B) telemetry via INA219/fuel-gauge addresses. | `--addresses 0x40 0x0b`, `--shunt-ohms` to override defaults. |
| `test_environmental.py` | Capture a single reading from the AHT20 + BMP280 combo sensor. | `--bus-id`, `--aht20-address`, `--bmp280-address`. |
| `test_pir.py` | Sample PIR motion sensor GPIO levels. | `--pins`, `--samples`, `--interval`. |
| `test_rgb_led.py` | Cycle the RGB LED channels to validate wiring. | `--rounds`, `--delay`. |
| `test_picamera.py` | Spin up Picamera2 and display capture stats. | `--preview`, `--resolution`. |
| `test_usb_camera.py` | Grab a JPEG frame from a USB camera via OpenCV. | `--device`, `--output`. |

Run any script with `--help` to see full usage options. Example:

```bash
python scripts/test_ups.py --addresses 0x40 0x0b --shunt-ohms 0.01
```

These helpers are safe to run repeatedly; they close devices and clean up GPIO state when finished.

> **Tip:** When the main server is running in `mode=run`, camera-facing scripts (`test_usb_camera.py`, `test_picamera.py`) may contend with the recording pipeline. Stop the run-mode service or wait until recordings finish before executing those scripts.

## Usage Cheatsheet

### `test_i2c_bus.py`
```bash
python scripts/test_i2c_bus.py --bus-id 1
```
Checks the specified I²C bus (default: `FEATHERFLAP_I2C_BUS_ID`) can be opened via smbus/smbus2.

### `test_ups.py`
```bash
python scripts/test_ups.py --bus-id 1 --addresses 0x40 0x0b
```
Tries each address in order until the UPS responds, printing VIN/VOUT/VBAT and temperature.

### `test_environmental.py`
```bash
python scripts/test_environmental.py --bus-id 1 --aht20-address 0x38 --bmp280-address 0x76
```
Reads the AHT20/BMP280 combo once and reports sensor values plus any per-device errors.

### `test_pir.py`
```bash
python scripts/test_pir.py --pins 17 27 --samples 5 --interval 0.5
```
Cycles through the configured PIR inputs and prints the HIGH/LOW state for each sample.

### `test_rgb_led.py`
```bash
python scripts/test_rgb_led.py --pins 24 23 18 --rounds 3 --hold 0.2
```
Sequentially toggles each RGB LED GPIO and reports progress, cleaning up pins afterwards.

### `test_picamera.py`
```bash
python scripts/test_picamera.py --preview-seconds 3
```
Initialises Picamera2, runs a preview for the requested duration, then shuts the camera down.

### `test_usb_camera.py`
```bash
python scripts/test_usb_camera.py --device 0 --width 1280 --height 720 --output frame.jpg
```
Captures a JPEG frame using OpenCV, prints the byte size, and optionally writes it to disk.
