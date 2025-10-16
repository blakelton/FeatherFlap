"""Utilities for interacting with the PiZ-UpTime UPS HAT."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Iterable, List

from .i2c import SMBusNotAvailable, open_bus

ADC_CHANNEL_BITS = {
    "vin": 0b11000001,  # Channel 0 (AIN0)
    "vout": 0b11010001,  # Channel 1 (AIN1)
    "vbat": 0b11100001,  # Channel 2 (AIN2)
    "temp": 0b11110001,  # Channel 3 (AIN3)
}
ADC_MAX_READING = 2047.0
ADC_VREF = 6.144


@dataclass
class UPSReadings:
    """Structured response returned when the UPS responds successfully."""

    address: int
    vin: float
    vout: float
    vbat: float
    temperature_c: float

    def to_dict(self) -> Dict[str, float | str]:
        return {
            "address": hex(self.address),
            "vin": round(self.vin, 3),
            "vout": round(self.vout, 3),
            "vbat": round(self.vbat, 3),
            "temperature_c": round(self.temperature_c, 2),
        }


def _read_channel_values(bus, address: int) -> Dict[str, float]:
    CONFIG_REG = 0x01
    CONVERSION_REG = 0x00
    values: Dict[str, float] = {}
    for name, cfg in ADC_CHANNEL_BITS.items():
        bus.write_byte_data(address, CONFIG_REG, cfg)
        time.sleep(0.003)
        raw = bus.read_word_data(address, CONVERSION_REG)
        scaled = (((raw & 0xFF) << 8) | ((raw & 0xFFF0) >> 8)) >> 4
        voltage = (scaled / ADC_MAX_READING) * ADC_VREF
        values[name] = voltage
    return values


def read_ups(bus_id: int, addresses: Iterable[int]) -> UPSReadings:
    """Attempt to read the UPS telemetry from the provided I²C addresses."""

    address_attempts: List[int] = list(dict.fromkeys(addresses))
    if not address_attempts:
        raise ValueError("At least one UPS I²C address must be provided.")

    try:
        with open_bus(bus_id) as bus:
            for address in address_attempts:
                try:
                    values = _read_channel_values(bus, address)
                except OSError:
                    continue
                temp_c = (4.0 - values["temp"]) / 0.0432
                return UPSReadings(
                    address=address,
                    vin=values["vin"],
                    vout=values["vout"],
                    vbat=values["vbat"],
                    temperature_c=temp_c,
                )
    except SMBusNotAvailable:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        # Propagate as runtime error to the caller for uniform handling.
        raise RuntimeError(f"Unexpected error reading UPS: {exc}") from exc

    attempted = ", ".join(hex(addr) for addr in address_attempts)
    raise RuntimeError(f"UPS did not respond on addresses: {attempted}")
