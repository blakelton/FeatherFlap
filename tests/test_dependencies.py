import importlib.util

import pytest

pytest.importorskip("pydantic")

from featherflap.config import (
    DEFAULT_AHT20_I2C_ADDRESS,
    DEFAULT_BMP280_I2C_ADDRESS,
    DEFAULT_I2C_BUS_ID,
)
from featherflap.hardware.camera import CameraUnavailable, capture_jpeg_frame
from featherflap.hardware.i2c import SMBusNotAvailable, has_smbus
from featherflap.hardware.sensors import read_environment


def test_environment_requires_smbus_when_missing() -> None:
    if has_smbus():
        pytest.skip("smbus available; hardware interaction requires device.")
    with pytest.raises(SMBusNotAvailable):
        read_environment(
            DEFAULT_I2C_BUS_ID,
            DEFAULT_AHT20_I2C_ADDRESS,
            DEFAULT_BMP280_I2C_ADDRESS,
        )


def test_capture_frame_requires_cv2_when_missing() -> None:
    if importlib.util.find_spec("cv2") is not None:
        pytest.skip("cv2 installed; cannot test missing dependency path.")
    with pytest.raises(CameraUnavailable):
        capture_jpeg_frame()
