"""Drivers for the AHT20 + BMP280 environmental sensor combo."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Tuple

from ..logger import get_logger
from .i2c import SMBusNotAvailable, open_bus

logger = get_logger(__name__)


@dataclass
class EnvironmentSnapshot:
    """Container for the latest environment readings."""

    results: Dict[str, Dict[str, float]] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)

    def healthy(self) -> bool:
        return not self.errors


class BMP280:
    """Minimal BMP280 driver for temperature and pressure."""

    CALIB_START = 0x88
    DATA_START = 0xF7
    CTRL_MEAS = 0xF4
    CONFIG = 0xF5

    def __init__(self, bus, address: int) -> None:
        self._bus = bus
        self._address = address
        self._cal = self._load_calibration()
        # Configure IIR filter off, standby time 500ms to reduce noise.
        self._bus.write_byte_data(self._address, self.CONFIG, 0xA0)
        # Store oversampling configuration (x1 for temp/pressure, sleep mode).
        self._ctrl_meas = 0x24
        logger.debug("Initialised BMP280 driver at address 0x%X", address)

    def _load_calibration(self):
        data = self._bus.read_i2c_block_data(self._address, self.CALIB_START, 24)

        def _u16(msb: int, lsb: int) -> int:
            return (msb << 8) | lsb

        def _s16(msb: int, lsb: int) -> int:
            value = _u16(msb, lsb)
            if value & 0x8000:
                value -= 0x10000
            return value

        return {
            "dig_T1": _u16(data[1], data[0]),
            "dig_T2": _s16(data[3], data[2]),
            "dig_T3": _s16(data[5], data[4]),
            "dig_P1": _u16(data[7], data[6]),
            "dig_P2": _s16(data[9], data[8]),
            "dig_P3": _s16(data[11], data[10]),
            "dig_P4": _s16(data[13], data[12]),
            "dig_P5": _s16(data[15], data[14]),
            "dig_P6": _s16(data[17], data[16]),
            "dig_P7": _s16(data[19], data[18]),
            "dig_P8": _s16(data[21], data[20]),
            "dig_P9": _s16(data[23], data[22]),
        }

    def _compensate_temperature(self, adc_T: int) -> Tuple[float, float]:
        c = self._cal
        var1 = (adc_T / 16384.0 - c["dig_T1"] / 1024.0) * c["dig_T2"]
        var2 = ((adc_T / 131072.0 - c["dig_T1"] / 8192.0) ** 2) * c["dig_T3"]
        t_fine = var1 + var2
        temperature = t_fine / 5120.0
        return temperature, t_fine

    def _compensate_pressure(self, adc_P: int, t_fine: float) -> float:
        c = self._cal
        var1 = t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * c["dig_P6"] / 32768.0
        var2 += var1 * c["dig_P5"] * 2.0
        var2 = var2 / 4.0 + c["dig_P4"] * 65536.0
        var1 = (c["dig_P3"] * var1 * var1 / 524288.0 + c["dig_P2"] * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * c["dig_P1"]
        if var1 == 0:
            raise ValueError("Invalid BMP280 calibration (division by zero).")
        pressure = 1048576.0 - adc_P
        pressure = ((pressure - var2 / 4096.0) * 6250.0) / var1
        var1 = c["dig_P9"] * pressure * pressure / 2147483648.0
        var2 = pressure * c["dig_P8"] / 32768.0
        pressure = pressure + (var1 + var2 + c["dig_P7"]) / 16.0
        return pressure

    def read(self) -> Tuple[float, float]:
        self._bus.write_byte_data(self._address, self.CTRL_MEAS, self._ctrl_meas | 0x01)
        time.sleep(0.01)
        data = self._bus.read_i2c_block_data(self._address, self.DATA_START, 6)
        adc_P = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        adc_T = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        temperature_c, t_fine = self._compensate_temperature(adc_T)
        pressure_pa = self._compensate_pressure(adc_P, t_fine)
        logger.debug("BMP280 reading: temperature=%0.2fC pressure=%0.2fhPa", temperature_c, pressure_pa / 100.0)
        return temperature_c, pressure_pa / 100.0


class AHT20:
    """Minimal AHT20 temperature and humidity driver."""

    def __init__(self, bus, address: int) -> None:
        self._bus = bus
        self._address = address
        self._bus.write_byte(self._address, 0xBA)  # soft reset
        time.sleep(0.02)
        self._bus.write_i2c_block_data(self._address, 0xBE, [0x08, 0x00])
        time.sleep(0.01)
        logger.debug("Initialised AHT20 driver at address 0x%X", address)

    def read(self) -> Tuple[float, float]:
        self._bus.write_i2c_block_data(self._address, 0xAC, [0x33, 0x00])
        time.sleep(0.08)
        for _ in range(5):
            data = self._bus.read_i2c_block_data(self._address, 0x00, 6)
            if data[0] & 0x80:
                time.sleep(0.01)
                continue
            raw_humidity = ((data[1] << 12) | (data[2] << 4) | (data[3] >> 4)) & 0xFFFFF
            raw_temperature = (((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]) & 0xFFFFF
            humidity = (raw_humidity / 1048576.0) * 100.0
            temperature = (raw_temperature / 1048576.0) * 200.0 - 50.0
            logger.debug("AHT20 reading: temperature=%0.2fC humidity=%0.2f%%", temperature, humidity)
            return temperature, humidity
        raise RuntimeError("AHT20 sensor timeout waiting for data readiness.")


def read_environment(bus_id: int, aht20_address: int, bmp280_address: int) -> EnvironmentSnapshot:
    """Read the temperature, humidity and pressure sensors."""

    snapshot = EnvironmentSnapshot()
    logger.debug(
        "Reading environment sensors on bus %s (AHT20=0x%X BMP280=0x%X)",
        bus_id,
        aht20_address,
        bmp280_address,
    )
    try:
        with open_bus(bus_id) as bus:
            try:
                aht20 = AHT20(bus, aht20_address)
                temp_c, humidity = aht20.read()
                snapshot.results["aht20"] = {
                    "temperature_c": round(temp_c, 2),
                    "humidity_pct": round(humidity, 2),
                }
            except Exception as exc:
                snapshot.errors["aht20"] = str(exc)
                logger.warning("AHT20 read failed: %s", exc)
            try:
                bmp280 = BMP280(bus, bmp280_address)
                temp_c, pressure_hpa = bmp280.read()
                snapshot.results["bmp280"] = {
                    "temperature_c": round(temp_c, 2),
                    "pressure_hpa": round(pressure_hpa, 2),
                }
            except Exception as exc:
                snapshot.errors["bmp280"] = str(exc)
                logger.warning("BMP280 read failed: %s", exc)
    except SMBusNotAvailable:
        logger.warning("SMBus not available when reading environment sensors")
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected error during environment read: %s", exc)
        raise RuntimeError(f"Unexpected error reading environment sensors: {exc}") from exc
    logger.info(
        "Environment read complete (results=%d errors=%d)",
        len(snapshot.results),
        len(snapshot.errors),
    )
    return snapshot
