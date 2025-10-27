"""Application configuration for FeatherFlap."""

from __future__ import annotations

import json
import logging
import os
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

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
DEFAULT_UPTIME_I2C_ADDRESSES = (0x40,)
DEFAULT_AHT20_I2C_ADDRESS = 0x38
DEFAULT_BMP280_I2C_ADDRESS = 0x76
DEFAULT_I2C_BUS_ID = 1
DEFAULT_UPTIME_SHUNT_RESISTANCE_OHMS = 0.01
DEFAULT_BATTERY_CAPACITY_MAH = 10000
DEFAULT_RECORDINGS_PATH = "recordings"
DEFAULT_RECORDING_MAX_SECONDS = 30
DEFAULT_RECORDING_MIN_GAP_SECONDS = 45
DEFAULT_MOTION_POLL_INTERVAL_SECONDS = 0.25
DEFAULT_CAMERA_RECORD_WIDTH = 1280
DEFAULT_CAMERA_RECORD_HEIGHT = 720
DEFAULT_CAMERA_RECORD_FPS = 15.0


class TemperatureUnit(str, Enum):
    """Display unit for temperature values."""

    CELSIUS = "celsius"
    FAHRENHEIT = "fahrenheit"
    KELVIN = "kelvin"


class OperationMode(str, Enum):
    """Overall application mode."""

    TEST = "test"
    RUN = "run"


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
    mode: OperationMode = Field(
        default=OperationMode.TEST,
        description="Operating mode for the service. 'test' exposes diagnostics; 'run' enables automated recording.",
    )
    camera_device: Optional[int] = Field(
        default=DEFAULT_CAMERA_DEVICE_INDEX,
        description="Default video device index for USB camera interactions.",
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
        description="I2C addresses to probe for UPS telemetry (Seengreat defaults to 0x40).",
    )
    uptime_shunt_resistance_ohms: float = Field(
        default=DEFAULT_UPTIME_SHUNT_RESISTANCE_OHMS,
        gt=0.0,
        description="Shunt resistor value (ohms) used by the UPS INA219 current sensor.",
    )
    battery_capacity_mah: float = Field(
        default=DEFAULT_BATTERY_CAPACITY_MAH,
        gt=0.0,
        description="Nominal battery capacity (mAh) used for runtime estimates.",
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
    recordings_path: Path = Field(
        default=Path(DEFAULT_RECORDINGS_PATH),
        description="Directory where run-mode recordings are stored.",
    )
    network_export_path: Optional[Path] = Field(
        default=None,
        description="Optional network or removable storage path to mirror finished recordings.",
    )
    recording_max_seconds: int = Field(
        default=DEFAULT_RECORDING_MAX_SECONDS,
        gt=0,
        description="Maximum length (seconds) of a single motion-triggered recording.",
    )
    recording_min_gap_seconds: int = Field(
        default=DEFAULT_RECORDING_MIN_GAP_SECONDS,
        ge=0,
        description="Cooldown period (seconds) after a recording before another can start.",
    )
    motion_poll_interval_seconds: float = Field(
        default=DEFAULT_MOTION_POLL_INTERVAL_SECONDS,
        gt=0.0,
        description="Polling interval (seconds) for motion detection when using PIR sensors.",
    )
    sleep_windows: list[Dict[str, str]] = Field(
        default_factory=list,
        description="List of quiet windows (\"HH:MM-HH:MM\") where run mode minimizes activity to save power.",
    )
    camera_record_width: int = Field(
        default=DEFAULT_CAMERA_RECORD_WIDTH,
        gt=0,
        description="Video recording width in pixels.",
    )
    camera_record_height: int = Field(
        default=DEFAULT_CAMERA_RECORD_HEIGHT,
        gt=0,
        description="Video recording height in pixels.",
    )
    camera_record_fps: float = Field(
        default=DEFAULT_CAMERA_RECORD_FPS,
        gt=0.0,
        description="Frame rate used for run-mode recordings.",
    )
    temperature_unit: TemperatureUnit = Field(
        default=TemperatureUnit.CELSIUS,
        description="Preferred display unit for temperature values in the UI.",
    )

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

    @field_validator("sleep_windows", mode="before")
    @classmethod
    def _parse_sleep_windows(cls, value: Any) -> list[Dict[str, str]]:
        """Normalise sleep window formats into a list of {'start': 'HH:MM', 'end': 'HH:MM'} dictionaries."""

        if value in (None, "", []):
            return []
        raw_windows: List[str | Dict[str, str]]
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = [value]
            raw_windows = parsed if isinstance(parsed, list) else [parsed]
        elif isinstance(value, (list, tuple)):
            raw_windows = list(value)
        else:
            raw_windows = [value]

        normalised: list[Dict[str, str]] = []
        for window in raw_windows:
            if isinstance(window, dict):
                start = window.get("start")
                end = window.get("end")
            elif isinstance(window, str):
                parts = window.split("-")
                if len(parts) != 2:
                    raise ValueError(f"Invalid sleep window format: {window!r}")
                start, end = parts[0].strip(), parts[1].strip()
            else:
                raise ValueError(f"Unsupported sleep window specification: {window!r}")
            if not start or not end:
                raise ValueError(f"Sleep window must include start and end times: {window!r}")
            normalised.append({"start": start, "end": end})
        return normalised


_DEFAULT_RUNTIME_PATH = Path(__file__).resolve().parents[2] / ".featherflap-settings.json"
RUNTIME_CONFIG_PATH = Path(os.getenv("FEATHERFLAP_RUNTIME_CONFIG", str(_DEFAULT_RUNTIME_PATH)))
PERSISTED_FIELDS = {
    "temperature_unit",
    "pir_pins",
    "motion_poll_interval_seconds",
    "camera_device",
    "camera_record_width",
    "camera_record_height",
    "camera_record_fps",
    "recordings_path",
    "recording_max_seconds",
    "recording_min_gap_seconds",
}

_SETTINGS_LOCK = RLock()
_SETTINGS: AppSettings | None = None


def _load_runtime_overrides() -> Dict[str, Any]:
    if not RUNTIME_CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(RUNTIME_CONFIG_PATH.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _write_runtime_overrides(overrides: Dict[str, Any]) -> None:
    try:
        RUNTIME_CONFIG_PATH.write_text(json.dumps(overrides, indent=2, sort_keys=True))
        except Exception:
            logger = logging.getLogger("featherflap.config")
            logger.warning("Failed to persist runtime configuration overrides to %s", RUNTIME_CONFIG_PATH)


def _load_settings() -> AppSettings:
    """Instantiate settings from the environment and runtime overrides."""

    base = AppSettings()
    overrides = _load_runtime_overrides()
    if overrides:
        try:
            base = base.model_copy(update=overrides, deep=True)
        except Exception:
            logger = logging.getLogger("featherflap.config")
            logger.warning("Ignoring invalid runtime overrides: %s", overrides)
    return base


def get_settings() -> AppSettings:
    """Return the current application settings, loading them if necessary."""

    global _SETTINGS
    with _SETTINGS_LOCK:
        if _SETTINGS is None:
            _SETTINGS = _load_settings()
        return _SETTINGS


def reload_settings() -> AppSettings:
    """Reload settings from the environment, replacing the current cache."""

    global _SETTINGS
    with _SETTINGS_LOCK:
        _SETTINGS = _load_settings()
        return _SETTINGS


def update_settings(changes: Dict[str, Any]) -> AppSettings:
    """Apply runtime overrides to the current settings."""

    global _SETTINGS
    with _SETTINGS_LOCK:
        current = get_settings()
        updated = current.model_copy(update=changes, deep=True)
        _SETTINGS = updated

        overrides = _load_runtime_overrides()
        for key in PERSISTED_FIELDS:
            if key in changes:
                value = getattr(updated, key)
                if isinstance(value, Path):
                    overrides[key] = str(value)
                else:
                    overrides[key] = value
        _write_runtime_overrides(overrides)

        return _SETTINGS


def convert_temperature(value_c: Optional[float], unit: TemperatureUnit) -> Optional[float]:
    """Convert a Celsius reading into the configured unit."""

    if value_c is None:
        return None
    if unit is TemperatureUnit.CELSIUS:
        return value_c
    if unit is TemperatureUnit.FAHRENHEIT:
        return value_c * 9.0 / 5.0 + 32.0
    if unit is TemperatureUnit.KELVIN:
        return value_c + 273.15
    return value_c
