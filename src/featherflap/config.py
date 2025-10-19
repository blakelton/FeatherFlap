"""Application configuration for FeatherFlap."""

import json
from functools import lru_cache
from typing import Any, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_LOG_LEVEL = "info"
DEFAULT_LOG_ERROR_ENABLED = True
DEFAULT_LOG_WARNING_ENABLED = True
DEFAULT_LOG_INFO_ENABLED = True
DEFAULT_LOG_DEBUG_ENABLED = False
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

    model_config = SettingsConfigDict(
        env_prefix="FEATHERFLAP_",
        env_file=".env",
        extra="ignore",
    )

    host: str = Field(default=DEFAULT_HOST, description="Interface for the API server.")
    port: int = Field(default=DEFAULT_PORT, description="Port for the API server.")
    reload: bool = Field(default=False, description="Enable auto-reload. Use only during development.")
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, description="Uvicorn log level.")
    log_error_enabled: bool = Field(
        default=DEFAULT_LOG_ERROR_ENABLED,
        description="Emit error-level log records.",
    )
    log_warning_enabled: bool = Field(
        default=DEFAULT_LOG_WARNING_ENABLED,
        description="Emit warning-level log records.",
    )
    log_info_enabled: bool = Field(
        default=DEFAULT_LOG_INFO_ENABLED,
        description="Emit information-level log records.",
    )
    log_debug_enabled: bool = Field(
        default=DEFAULT_LOG_DEBUG_ENABLED,
        description="Emit debug-level log records.",
    )
    allowed_origins: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_ORIGINS),
        description="CORS origins allowed to access the API.",
    )
    camera_device: Optional[int] = Field(
        default=DEFAULT_CAMERA_DEVICE_INDEX,
        description="Default video device index for USB camera tests.",
    )
    pir_pins: list[int] | str = Field(
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

    @field_validator("pir_pins", mode="before")
    @classmethod
    def _parse_pir_pins(cls, value: Any) -> list[int]:
        """Accept flexible formats (plain numbers, comma/space-separated, JSON array) for PIR pin lists."""

        if value is None or value == "":
            return []
        if isinstance(value, (list, tuple, set)):
            return [int(item, 0) if isinstance(item, str) else int(item) for item in value]
        if isinstance(value, (int, float)):
            return [int(value)]
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                tokens = [token for token in raw.replace(",", " ").split() if token]
                if not tokens:
                    return []
                try:
                    return [int(token, 0) for token in tokens]
                except ValueError as exc:  # pragma: no cover - defensive
                    raise ValueError(f"Invalid PIR pin specification: {value}") from exc
            else:
                if isinstance(parsed, (int, float)):
                    return [int(parsed)]
                if isinstance(parsed, str):
                    return [int(parsed, 0)]
                if isinstance(parsed, (list, tuple, set)):
                    try:
                        return [int(item, 0) if isinstance(item, str) else int(item) for item in parsed]
                    except ValueError as exc:  # pragma: no cover - defensive
                        raise ValueError(f"Invalid PIR pin list: {value}") from exc
            raise ValueError(f"Unsupported PIR pin format: {value}")
        raise ValueError(f"Unsupported PIR pin type: {type(value)!r}")


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings."""

    return AppSettings()
