"""Concrete hardware diagnostics for FeatherFlap."""

from __future__ import annotations

import os
import platform
import socket
import time
from contextlib import suppress
from typing import Dict, Iterable, List, Optional

from ..config import (
    DEFAULT_CAMERA_DEVICE_INDEX,
    DEFAULT_UPTIME_I2C_ADDRESSES,
    get_settings,
)
from .base import HardwareStatus, HardwareTest, HardwareTestResult
from .camera import CameraUnavailable, capture_jpeg_frame
from .i2c import SMBusNotAvailable, has_smbus, open_bus
from .power import read_ups
from .sensors import read_environment


SMBUS_COMPONENT_I2C = "I2C"
SMBUS_COMPONENT_UPS = "UPS"
SMBUS_COMPONENT_ENVIRONMENTAL = "environmental"
SMBUS_SKIP_MESSAGE_TEMPLATE = "smbus/smbus2 not installed – skipping {component} diagnostics."
PICAMERA_SKIP_MESSAGE = "picamera2 not available – skipping CSI camera test."
PIR_SKIP_MESSAGE = "RPi.GPIO not available – skipping PIR diagnostics."
RGB_LED_SKIP_MESSAGE = "RPi.GPIO not available – skipping RGB LED test."
RGB_LED_TOGGLE_DELAY_SECONDS = 0.15


def _skipped_result(test: HardwareTest, summary: str, details: Optional[Dict[str, object]] = None) -> HardwareTestResult:
    """Return a standardised skipped result for dependency issues."""

    return HardwareTestResult(
        id=test.id,
        name=test.name,
        status=HardwareStatus.SKIPPED,
        summary=summary,
        details=details or {},
    )


class SystemInfoTest(HardwareTest):
    id = "system-info"
    name = "System Information"
    description = "Collect baseline OS and hardware information."
    category = "system"

    def run(self) -> HardwareTestResult:
        data = {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "hostname": socket.gethostname(),
        }
        summary = f"Running on {data['platform']} (Python {data['python_version']})"
        return HardwareTestResult(
            id=self.id,
            name=self.name,
            status=HardwareStatus.OK,
            summary=summary,
            details=data,
        )


class I2CBusTest(HardwareTest):
    id = "i2c-bus"
    name = "I2C Bus"
    description = "Verify that the primary I2C bus opens successfully."
    category = "sensors"

    def run(self) -> HardwareTestResult:
        settings = get_settings()
        if not has_smbus():
            return _skipped_result(
                self,
                SMBUS_SKIP_MESSAGE_TEMPLATE.format(component=SMBUS_COMPONENT_I2C),
            )
        try:
            with open_bus(settings.i2c_bus_id):
                pass
        except FileNotFoundError as exc:
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary=f"I2C bus {settings.i2c_bus_id} not found.",
                details={"error": str(exc)},
            )
        except SMBusNotAvailable:
            return _skipped_result(
                self,
                SMBUS_SKIP_MESSAGE_TEMPLATE.format(component=SMBUS_COMPONENT_I2C),
            )
        except Exception as exc:  # pragma: no cover - defensive
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Unexpected error opening the I2C bus.",
                details={"error": str(exc)},
            )
        return HardwareTestResult(
            id=self.id,
            name=self.name,
            status=HardwareStatus.OK,
            summary=f"I2C bus {settings.i2c_bus_id} opened successfully.",
        )


class PiZUpTimeTest(HardwareTest):
    id = "ups"
    name = "PiZ-UpTime UPS"
    description = "Read voltages and board temperature from the PiZ-UpTime HAT."
    category = "power"

    def run(self) -> HardwareTestResult:
        settings = get_settings()
        if not has_smbus():
            return _skipped_result(
                self,
                SMBUS_SKIP_MESSAGE_TEMPLATE.format(component=SMBUS_COMPONENT_UPS),
            )

        addresses: List[int] = list(settings.uptime_i2c_addresses or [])
        env_addr = os.getenv("UPTIME_I2C_ADDR")
        if env_addr:
            with suppress(ValueError):
                addresses.insert(0, int(env_addr, 0))
        if not addresses:
            addresses = list(DEFAULT_UPTIME_I2C_ADDRESSES)
        try:
            readings = read_ups(settings.i2c_bus_id, addresses)
        except SMBusNotAvailable:
            return _skipped_result(
                self,
                SMBUS_SKIP_MESSAGE_TEMPLATE.format(component=SMBUS_COMPONENT_UPS),
            )
        except RuntimeError as exc:
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Unable to read from the PiZ-UpTime UPS.",
                details={"error": str(exc), "addresses": [hex(a) for a in addresses]},
            )
        return HardwareTestResult(
            id=self.id,
            name=self.name,
            status=HardwareStatus.OK,
            summary=f"UPS responded at {hex(readings.address)}.",
            details=readings.to_dict(),
        )


class EnvironmentalSensorTest(HardwareTest):
    id = "environmental"
    name = "AHT20 + BMP280 Environmental Sensors"
    description = "Read temperature, humidity, and pressure from the combo module."
    category = "sensors"

    def run(self) -> HardwareTestResult:
        settings = get_settings()
        if not has_smbus():
            return _skipped_result(
                self,
                SMBUS_SKIP_MESSAGE_TEMPLATE.format(component=SMBUS_COMPONENT_ENVIRONMENTAL),
            )
        try:
            snapshot = read_environment(
                settings.i2c_bus_id,
                settings.aht20_i2c_address,
                settings.bmp280_i2c_address,
            )
        except SMBusNotAvailable:
            return _skipped_result(
                self,
                SMBUS_SKIP_MESSAGE_TEMPLATE.format(component=SMBUS_COMPONENT_ENVIRONMENTAL),
            )
        except RuntimeError as exc:
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Environmental sensor read raised an unexpected error.",
                details={"error": str(exc)},
            )

        if snapshot.errors and not snapshot.results:
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Unable to communicate with AHT20 or BMP280 sensors.",
                details={"errors": snapshot.errors},
            )
        if snapshot.errors:
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.WARNING,
                summary="Partial sensor read success.",
                details={"results": snapshot.results, "errors": snapshot.errors},
            )
        return HardwareTestResult(
            id=self.id,
            name=self.name,
            status=HardwareStatus.OK,
            summary="AHT20 and BMP280 sensors responded successfully.",
            details=snapshot.results,
        )


class PicameraTest(HardwareTest):
    id = "picamera"
    name = "Pi Camera Module"
    description = "Initialise the CSI camera via Picamera2."
    category = "imaging"

    def run(self) -> HardwareTestResult:
        try:
            from picamera2 import Picamera2  # type: ignore
        except ImportError:
            return _skipped_result(self, PICAMERA_SKIP_MESSAGE)
        try:
            camera = Picamera2()
            camera.close()
        except Exception as exc:
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Failed to initialise Picamera2.",
                details={"error": str(exc)},
            )
        return HardwareTestResult(
            id=self.id,
            name=self.name,
            status=HardwareStatus.OK,
            summary="Picamera2 initialised successfully.",
        )


class UsbCameraTest(HardwareTest):
    id = "usb-camera"
    name = "USB Camera"
    description = "Capture a JPEG frame from the USB camera."
    category = "imaging"

    def run(self) -> HardwareTestResult:
        settings = get_settings()
        device_index = settings.camera_device if settings.camera_device is not None else DEFAULT_CAMERA_DEVICE_INDEX
        try:
            frame = capture_jpeg_frame(device_index)
        except CameraUnavailable as exc:
            return _skipped_result(self, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="USB camera capture raised an unexpected error.",
                details={"error": str(exc)},
            )
        return HardwareTestResult(
            id=self.id,
            name=self.name,
            status=HardwareStatus.OK,
            summary=f"Captured {len(frame)} bytes from USB camera.",
        )


class PIRSensorTest(HardwareTest):
    id = "pir"
    name = "PIR Motion Sensors"
    description = "Read the digital state of configured PIR motion sensors."
    category = "sensors"

    def run(self) -> HardwareTestResult:
        try:
            import RPi.GPIO as GPIO  # type: ignore
        except ImportError:
            return _skipped_result(self, PIR_SKIP_MESSAGE)

        settings = get_settings()
        pins = settings.pir_pins
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        states: Dict[int, int] = {}
        try:
            for pin in pins:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
                states[pin] = GPIO.input(pin)
        except Exception as exc:
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Failed to read PIR sensors.",
                details={"error": str(exc)},
            )
        finally:
            for pin in pins:
                with suppress(Exception):
                    GPIO.cleanup(pin)
        summary_bits = ", ".join(f"GPIO{pin}={'HIGH' if val else 'LOW'}" for pin, val in states.items())
        return HardwareTestResult(
            id=self.id,
            name=self.name,
            status=HardwareStatus.OK,
            summary=f"PIR sensors read successfully: {summary_bits}",
            details={"states": states},
        )


class RGBLedTest(HardwareTest):
    id = "rgb-led"
    name = "RGB LED"
    description = "Flash the RGB LED channels sequentially."
    category = "actuators"

    def run(self) -> HardwareTestResult:
        try:
            import RPi.GPIO as GPIO  # type: ignore
        except ImportError:
            return _skipped_result(self, RGB_LED_SKIP_MESSAGE)

        settings = get_settings()
        pins = settings.rgb_led_pins
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        try:
            for pin in pins:
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
            for pin in pins:
                GPIO.output(pin, GPIO.HIGH)
                time.sleep(RGB_LED_TOGGLE_DELAY_SECONDS)
                GPIO.output(pin, GPIO.LOW)
        except Exception as exc:
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Failed to toggle RGB LED pins.",
                details={"error": str(exc)},
            )
        finally:
            for pin in pins:
                with suppress(Exception):
                    GPIO.cleanup(pin)
        return HardwareTestResult(
            id=self.id,
            name=self.name,
            status=HardwareStatus.OK,
            summary="RGB LED toggled successfully.",
            details={"pins": pins},
        )


def default_tests() -> List[HardwareTest]:
    """Return the default suite of hardware diagnostics."""

    return [
        SystemInfoTest(),
        I2CBusTest(),
        PiZUpTimeTest(),
        EnvironmentalSensorTest(),
        PicameraTest(),
        UsbCameraTest(),
        PIRSensorTest(),
        RGBLedTest(),
    ]
