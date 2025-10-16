"""Hardware diagnostic suite for FeatherFlap."""

from .base import HardwareStatus, HardwareTest, HardwareTestResult
from .camera import CameraUnavailable, capture_jpeg_frame, mjpeg_stream
from .power import UPSReadings, read_ups
from .registry import HardwareTestRegistry
from .sensors import EnvironmentSnapshot, read_environment
from .tests import default_tests

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
    "CameraUnavailable",
    "capture_jpeg_frame",
    "mjpeg_stream",
]
