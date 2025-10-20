"""Hardware diagnostic suite for FeatherFlap."""

from ..logger import get_logger
from .base import HardwareStatus, HardwareTest, HardwareTestResult
from .camera import CameraUnavailable, capture_jpeg_frame, mjpeg_stream
from .battery import BatteryEstimate, BatteryEstimator, voltage_to_soc
from .power import UPSReadings, read_ups
from .registry import HardwareTestRegistry
from .sensors import EnvironmentSnapshot, read_environment
from .tests import default_tests

get_logger(__name__).debug("Hardware diagnostic package loaded")

__all__ = [
    "HardwareStatus",
    "HardwareTest",
    "HardwareTestResult",
    "HardwareTestRegistry",
    "default_tests",
    "EnvironmentSnapshot",
    "read_environment",
    "UPSReadings",
    "read_ups",
    "BatteryEstimate",
    "BatteryEstimator",
    "voltage_to_soc",
    "CameraUnavailable",
    "capture_jpeg_frame",
    "mjpeg_stream",
]
