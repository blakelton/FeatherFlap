"""Application configuration for FeatherFlap."""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_LOG_LEVEL = "info"
DEFAULT_ALLOWED_ORIGINS = ("*",)
DEFAULT_CAMERA_DEVICE_INDEX = 0
DEFAULT_PIR_PINS = (17, 27)
DEFAULT_RGB_LED_PINS = (24, 23, 18)
DEFAULT_UPTIME_I2C_ADDRESSES = (0x48, 0x49, 0x4B)
DEFAULT_AHT20_I2C_ADDRESS = 0x38
DEFAULT_BMP280_I2C_ADDRESS = 0x76
DEFAULT_I2C_BUS_ID = 1


class AppSettings(BaseSettings):
    """Settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="FEATHERFLAP_", env_file=".env", extra="ignore")

    host: str = Field(default=DEFAULT_HOST, description="Interface for the API server.")
    port: int = Field(default=DEFAULT_PORT, description="Port for the API server.")
    reload: bool = Field(default=False, description="Enable auto-reload. Use only during development.")
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, description="Uvicorn log level.")
    allowed_origins: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_ORIGINS),
        description="CORS origins allowed to access the API.",
    )
    camera_device: Optional[int] = Field(
        default=DEFAULT_CAMERA_DEVICE_INDEX,
        description="Default video device index for USB camera tests.",
    )
    pir_pins: list[int] = Field(
        default_factory=lambda: list(DEFAULT_PIR_PINS),
        description="BCM pins for PIR sensors.",
    )
    rgb_led_pins: tuple[int, int, int] = Field(
        default=DEFAULT_RGB_LED_PINS,
        description="BCM pins for the RGB LED in order (red, green, blue).",
    )
    uptime_i2c_addresses: list[int] = Field(
        default_factory=lambda: list(DEFAULT_UPTIME_I2C_ADDRESSES),
        description="I2C addresses to probe for the PiZ-UpTime HAT.",
    )
    aht20_i2c_address: int = Field(
        default=DEFAULT_AHT20_I2C_ADDRESS,
        description="I2C address for the AHT20 temp/humidity sensor.",
    )
    bmp280_i2c_address: int = Field(
        default=DEFAULT_BMP280_I2C_ADDRESS,
        description="I2C address for the BMP280 pressure sensor.",
    )
    i2c_bus_id: int = Field(default=DEFAULT_I2C_BUS_ID, description="I2C bus number to use for Raspberry Pi sensors.")


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings."""

    return AppSettings()
