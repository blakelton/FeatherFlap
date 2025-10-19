"""Utilities for interacting with the Seengreat Pi Zero UPS HAT (B)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from ..logger import get_logger
from .i2c import SMBusNotAvailable, open_bus

INA219_REG_CONFIG = 0x00
INA219_REG_SHUNT_VOLTAGE = 0x01
INA219_REG_BUS_VOLTAGE = 0x02

INA219_BUS_VOLTAGE_LSB = 0.004  # 4 mV
INA219_SHUNT_VOLTAGE_LSB = 0.00001  # 10 µV

logger = get_logger(__name__)


@dataclass
class UPSReadings:
    """Structured response returned when the UPS responds successfully."""

    address: int
    bus_voltage_v: float
    shunt_voltage_mv: Optional[float] = None
    current_ma: Optional[float] = None
    power_mw: Optional[float] = None

    def to_dict(self) -> Dict[str, float | str]:
        payload: Dict[str, float | str] = {
            "address": hex(self.address),
            "bus_voltage_v": round(self.bus_voltage_v, 3),
        }
        if self.shunt_voltage_mv is not None:
            payload["shunt_voltage_mv"] = round(self.shunt_voltage_mv, 3)
        if self.current_ma is not None:
            payload["current_ma"] = round(self.current_ma, 2)
        if self.power_mw is not None:
            payload["power_mw"] = round(self.power_mw, 2)
        return payload


def _read_word_be(bus, address: int, register: int) -> int:
    """Read a big-endian 16-bit register from the INA219."""

    raw = bus.read_word_data(address, register)
    value = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)
    logger.debug("Read register 0x%02X from 0x%X: 0x%04X", register, address, value)
    return value


def _read_signed_word_be(bus, address: int, register: int) -> int:
    value = _read_word_be(bus, address, register)
    if value & 0x8000:
        value -= 0x10000
    return value


def _read_ina219(bus, address: int, shunt_resistance_ohms: float) -> UPSReadings:
    # Validate device by reading the config register; failure raises OSError.
    _ = _read_word_be(bus, address, INA219_REG_CONFIG)

    bus_voltage_raw = _read_word_be(bus, address, INA219_REG_BUS_VOLTAGE)
    bus_voltage_reg = (bus_voltage_raw >> 3) & 0x1FFF
    bus_voltage_v = bus_voltage_reg * INA219_BUS_VOLTAGE_LSB

    shunt_voltage_raw = _read_signed_word_be(bus, address, INA219_REG_SHUNT_VOLTAGE)
    shunt_voltage_v = shunt_voltage_raw * INA219_SHUNT_VOLTAGE_LSB
    shunt_voltage_mv = shunt_voltage_v * 1000.0

    current_ma: Optional[float] = None
    power_mw: Optional[float] = None
    if shunt_resistance_ohms > 0:
        current_ma = shunt_voltage_v / shunt_resistance_ohms * 1000.0
        power_mw = bus_voltage_v * current_ma

    return UPSReadings(
        address=address,
        bus_voltage_v=bus_voltage_v,
        shunt_voltage_mv=shunt_voltage_mv,
        current_ma=current_ma,
        power_mw=power_mw,
    )


def read_ups(bus_id: int, addresses: Iterable[int], shunt_resistance_ohms: float = 0.01) -> UPSReadings:
    """Attempt to read UPS telemetry from the provided I²C addresses."""

    address_attempts: List[int] = list(dict.fromkeys(addresses))
    if not address_attempts:
        logger.error("UPS read requested without addresses")
        raise ValueError("At least one UPS I²C address must be provided.")

    logger.debug(
        "Attempting UPS read on bus %s for addresses %s (shunt=%.5fΩ)",
        bus_id,
        [hex(addr) for addr in address_attempts],
        shunt_resistance_ohms,
    )
    try:
        with open_bus(bus_id) as bus:
            for address in address_attempts:
                try:
                    readings = _read_ina219(bus, address, shunt_resistance_ohms)
                except OSError as exc:
                    logger.debug("UPS did not respond at address %s: %s", hex(address), exc)
                    continue
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Unexpected INA219 read failure at %s: %s", hex(address), exc)
                    continue
                logger.info(
                    "UPS responded at address %s (bus=%.2fV current=%s)",
                    hex(readings.address),
                    readings.bus_voltage_v,
                    f"{readings.current_ma:.1f}mA" if readings.current_ma is not None else "n/a",
                )
                return readings
    except SMBusNotAvailable:
        logger.warning("SMBus not available while reading UPS")
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected error during UPS read: %s", exc)
        raise RuntimeError(f"Unexpected error reading UPS: {exc}") from exc

    attempted = ", ".join(hex(addr) for addr in address_attempts)
    logger.error("UPS did not respond on any addresses: %s", attempted)
    raise RuntimeError(f"UPS did not respond on addresses: {attempted}")
