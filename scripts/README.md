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
| `test_ups.py` | Poll the Seengreat Pi Zero UPS HAT (B) telemetry via INA219/fuel-gauge addresses. | `--addresses 0x40 0x0b` to target specific devices. |
| `test_environmental.py` | Capture a single reading from the AHT20 + BMP280 combo sensor. | `--bus-id`, `--aht20-address`, `--bmp280-address`. |
| `test_pir.py` | Sample PIR motion sensor GPIO levels. | `--pins`, `--samples`, `--interval`. |
| `test_rgb_led.py` | Cycle the RGB LED channels to validate wiring. | `--rounds`, `--delay`. |
| `test_picamera.py` | Spin up Picamera2 and display capture stats. | `--preview`, `--resolution`. |
| `test_usb_camera.py` | Grab a JPEG frame from a USB camera via OpenCV. | `--device-index`, `--output`. |

Run any script with `--help` to see full usage options. Example:

```bash
python scripts/test_ups.py --addresses 0x40 0x0b --samples 5
```

These helpers are safe to run repeatedly; they close devices and clean up GPIO state when finished.
