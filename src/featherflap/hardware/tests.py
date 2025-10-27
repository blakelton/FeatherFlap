"""Concrete hardware diagnostics for FeatherFlap."""

from __future__ import annotations

import os
import platform
import socket
from contextlib import suppress
from typing import Dict, Iterable, List, Optional

from ..config import DEFAULT_CAMERA_DEVICE_INDEX, DEFAULT_UPTIME_I2C_ADDRESSES, OperationMode, get_settings
from ..logger import get_logger
from .base import HardwareStatus, HardwareTest, HardwareTestResult
from .camera import CameraUnavailable, capture_jpeg_frame
from .i2c import SMBusNotAvailable, has_smbus, open_bus
from .pir import PIRUnavailable, read_pir_states
from .power import read_ups
from .rgb_led import RGBLedUnavailable, flash_rgb_led_sequence
from .sensors import read_environment


SMBUS_COMPONENT_I2C = "I2C"
SMBUS_COMPONENT_UPS = "UPS"
SMBUS_COMPONENT_ENVIRONMENTAL = "environmental"
SMBUS_SKIP_MESSAGE_TEMPLATE = "smbus/smbus2 not installed – skipping {component} diagnostics."
PICAMERA_SKIP_MESSAGE = "picamera2 not available – skipping CSI camera test."
PIR_SKIP_MESSAGE = "RPi.GPIO not available – skipping PIR diagnostics."
RGB_LED_SKIP_MESSAGE = "RPi.GPIO not available – skipping RGB LED test."
RGB_LED_TOGGLE_DELAY_SECONDS = 0.15

logger = get_logger(__name__)


def _skipped_result(test: HardwareTest, summary: str, details: Optional[Dict[str, object]] = None) -> HardwareTestResult:
    """Return a standardised skipped result for dependency issues."""

    logger.info("Skipping test '%s': %s", test.id, summary)
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
        logger.debug("Collecting system information for diagnostic")
        data = {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "hostname": socket.gethostname(),
        }
        summary = f"Running on {data['platform']} (Python {data['python_version']})"
        logger.info("System information gathered: %s", summary)
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
        logger.debug("Running I2C bus diagnostic on bus %s", settings.i2c_bus_id)
        if not has_smbus():
            logger.warning("SMBus library unavailable; skipping I2C bus diagnostic")
            return _skipped_result(
                self,
                SMBUS_SKIP_MESSAGE_TEMPLATE.format(component=SMBUS_COMPONENT_I2C),
            )
        try:
            with open_bus(settings.i2c_bus_id):
                pass
        except FileNotFoundError as exc:
            logger.error("I2C bus %s not found: %s", settings.i2c_bus_id, exc)
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary=f"I2C bus {settings.i2c_bus_id} not found.",
                details={"error": str(exc)},
            )
        except SMBusNotAvailable:
            logger.warning("SMBus not available during I2C bus diagnostic run")
            return _skipped_result(
                self,
                SMBUS_SKIP_MESSAGE_TEMPLATE.format(component=SMBUS_COMPONENT_I2C),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Unexpected error opening I2C bus %s: %s", settings.i2c_bus_id, exc)
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Unexpected error opening the I2C bus.",
                details={"error": str(exc)},
            )
        logger.info("I2C bus %s opened successfully", settings.i2c_bus_id)
        return HardwareTestResult(
            id=self.id,
            name=self.name,
            status=HardwareStatus.OK,
            summary=f"I2C bus {settings.i2c_bus_id} opened successfully.",
        )


class SeengreatUPSTest(HardwareTest):
    id = "ups"
    name = "Seengreat UPS Module"
    description = "Read bus voltage and current from the Seengreat Pi Zero UPS HAT (B)."
    category = "power"

    def run(self) -> HardwareTestResult:
        settings = get_settings()
        logger.debug("Running UPS diagnostic on bus %s", settings.i2c_bus_id)
        if not has_smbus():
            logger.warning("SMBus library unavailable; skipping UPS diagnostic")
            return _skipped_result(
                self,
                SMBUS_SKIP_MESSAGE_TEMPLATE.format(component=SMBUS_COMPONENT_UPS),
            )

        addresses: List[int] = list(settings.uptime_i2c_addresses or [])
        env_addr = os.getenv("UPTIME_I2C_ADDR")
        if env_addr:
            with suppress(ValueError):
                addresses.insert(0, int(env_addr, 0))
                logger.info("Using UPTIME_I2C_ADDR override: %s", env_addr)
        if not addresses:
            addresses = list(DEFAULT_UPTIME_I2C_ADDRESSES)
        logger.debug("UPS diagnostic probing addresses: %s", [hex(a) for a in addresses])
        try:
            readings = read_ups(
                settings.i2c_bus_id,
                addresses,
                settings.uptime_shunt_resistance_ohms,
            )
        except SMBusNotAvailable:
            logger.warning("SMBus not available during UPS diagnostic run")
            return _skipped_result(
                self,
                SMBUS_SKIP_MESSAGE_TEMPLATE.format(component=SMBUS_COMPONENT_UPS),
            )
        except RuntimeError as exc:
            logger.error("UPS diagnostic failed: %s", exc)
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Unable to read from the UPS telemetry chip.",
                details={"error": str(exc), "addresses": [hex(a) for a in addresses]},
            )
        logger.info(
            "UPS diagnostic succeeded at address %s (bus=%.2fV current=%s)",
            hex(readings.address),
            readings.bus_voltage_v,
            f"{readings.current_ma:.1f}mA" if readings.current_ma is not None else "n/a",
        )
        if readings.current_ma is not None:
            summary = (
                f"UPS {hex(readings.address)} bus {readings.bus_voltage_v:.2f} V, "
                f"{readings.current_ma:.1f} mA."
            )
        else:
            summary = f"UPS {hex(readings.address)} bus {readings.bus_voltage_v:.2f} V."
        return HardwareTestResult(
            id=self.id,
            name=self.name,
            status=HardwareStatus.OK,
            summary=summary,
            details=readings.to_dict(),
        )


class EnvironmentalSensorTest(HardwareTest):
    id = "environmental"
    name = "AHT20 + BMP280 Environmental Sensors"
    description = "Read temperature, humidity, and pressure from the combo module."
    category = "sensors"

    def run(self) -> HardwareTestResult:
        settings = get_settings()
        logger.debug(
            "Running environmental diagnostic on bus %s (AHT20=0x%X BMP280=0x%X)",
            settings.i2c_bus_id,
            settings.aht20_i2c_address,
            settings.bmp280_i2c_address,
        )
        if not has_smbus():
            logger.warning("SMBus library unavailable; skipping environmental diagnostic")
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
            logger.warning("SMBus not available during environmental diagnostic run")
            return _skipped_result(
                self,
                SMBUS_SKIP_MESSAGE_TEMPLATE.format(component=SMBUS_COMPONENT_ENVIRONMENTAL),
            )
        except RuntimeError as exc:
            logger.error("Environmental diagnostic failed: %s", exc)
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Environmental sensor read raised an unexpected error.",
                details={"error": str(exc)},
            )

        if snapshot.errors and not snapshot.results:
            logger.error("Environmental diagnostic unable to reach sensors: %s", snapshot.errors)
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Unable to communicate with AHT20 or BMP280 sensors.",
                details={"errors": snapshot.errors},
            )
        if snapshot.errors:
            logger.warning("Environmental diagnostic partial success: %s", snapshot.errors)
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.WARNING,
                summary="Partial sensor read success.",
                details={"results": snapshot.results, "errors": snapshot.errors},
            )
        logger.info("Environmental diagnostic succeeded with readings: %s", snapshot.results)
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
        logger.debug("Running Picamera diagnostic")
        try:
            from picamera2 import Picamera2  # type: ignore
        except ImportError:
            logger.warning("Picamera2 not installed; skipping Picamera diagnostic")
            return _skipped_result(self, PICAMERA_SKIP_MESSAGE)
        try:
            camera = Picamera2()
            camera.close()
        except Exception as exc:
            logger.error("Picamera diagnostic failed: %s", exc)
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Failed to initialise Picamera2.",
                details={"error": str(exc)},
            )
        logger.info("Picamera diagnostic succeeded")
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
        logger.debug("Running USB camera diagnostic on device %s", device_index)
        try:
            frame = capture_jpeg_frame(device_index)
        except CameraUnavailable as exc:
            logger.warning("USB camera diagnostic skipped: %s", exc)
            return _skipped_result(self, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("USB camera diagnostic failed: %s", exc)
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="USB camera capture raised an unexpected error.",
                details={"error": str(exc)},
            )
        logger.info("USB camera diagnostic captured %d bytes", len(frame))
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
        logger.debug("Running PIR sensor diagnostic")
        settings = get_settings()
        pins = settings.pir_pins
        try:
            states = read_pir_states(pins)
        except PIRUnavailable as exc:
            logger.warning("PIR diagnostic skipped: %s", exc)
            return _skipped_result(self, PIR_SKIP_MESSAGE)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Unexpected PIR diagnostic failure: %s", exc)
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Failed to read PIR sensors.",
                details={"error": str(exc)},
            )
        summary_bits = ", ".join(f"GPIO{pin}={'HIGH' if val else 'LOW'}" for pin, val in states.items())
        logger.info("PIR sensor diagnostic succeeded: %s", summary_bits)
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
        logger.debug("Running RGB LED diagnostic")
        settings = get_settings()
        pins = settings.rgb_led_pins
        try:
            flash_rgb_led_sequence(pins, RGB_LED_TOGGLE_DELAY_SECONDS)
        except RGBLedUnavailable as exc:
            logger.warning("RGB LED diagnostic skipped: %s", exc)
            return _skipped_result(self, RGB_LED_SKIP_MESSAGE)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Unexpected RGB LED diagnostic failure: %s", exc)
            return HardwareTestResult(
                id=self.id,
                name=self.name,
                status=HardwareStatus.ERROR,
                summary="Failed to toggle RGB LED pins.",
                details={"error": str(exc)},
            )
        logger.info("RGB LED diagnostic toggled pins %s", pins)
        return HardwareTestResult(
            id=self.id,
            name=self.name,
            status=HardwareStatus.OK,
            summary="RGB LED toggled successfully.",
            details={"pins": pins},
        )


def default_tests() -> List[HardwareTest]:
    """Return the default suite of hardware diagnostics."""

    logger.debug("Creating default hardware diagnostic suite")
    settings = get_settings()
    suite: List[HardwareTest] = [
        SystemInfoTest(),
        I2CBusTest(),
        SeengreatUPSTest(),
        EnvironmentalSensorTest(),
        PicameraTest(),
        UsbCameraTest(),
        PIRSensorTest(),
        RGBLedTest(),
    ]
    if settings.mode == OperationMode.RUN:
        suite = [test for test in suite if not isinstance(test, (PicameraTest, UsbCameraTest))]
        logger.debug("Run mode detected; camera diagnostics removed from default suite")
    logger.info("Initialised default hardware diagnostic suite with %d tests", len(suite))
    return suite
