"""Application configuration for FeatherFlap."""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="FEATHERFLAP_", env_file=".env", extra="ignore")

    host: str = Field(default="0.0.0.0", description="Interface for the API server.")
    port: int = Field(default=8000, description="Port for the API server.")
    reload: bool = Field(default=False, description="Enable auto-reload. Use only during development.")
    log_level: str = Field(default="info", description="Uvicorn log level.")
    allowed_origins: list[str] = Field(
        default=["*"],
        description="CORS origins allowed to access the API.",
    )
    camera_device: Optional[int] = Field(default=0, description="Default video device index for USB camera tests.")
    pir_pins: list[int] = Field(default_factory=lambda: [17, 27], description="BCM pins for PIR sensors.")
    rgb_led_pins: tuple[int, int, int] = Field(
        default=(24, 23, 18),
        description="BCM pins for the RGB LED in order (red, green, blue).",
    )
    uptime_i2c_addresses: list[int] = Field(
        default_factory=lambda: [0x48, 0x49, 0x4B],
        description="I2C addresses to probe for the PiZ-UpTime HAT.",
    )
    aht20_i2c_address: int = Field(default=0x38, description="I2C address for the AHT20 temp/humidity sensor.")
    bmp280_i2c_address: int = Field(default=0x76, description="I2C address for the BMP280 pressure sensor.")
    i2c_bus_id: int = Field(default=1, description="I2C bus number to use for Raspberry Pi sensors.")


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings."""

    return AppSettings()
