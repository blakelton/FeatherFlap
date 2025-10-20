"""Learning-based battery estimation utilities."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

DEFAULT_DATA_DIR = Path.home() / ".local/share/featherflap"
STATE_FILENAME = "battery_state.json"
HISTORY_FILENAME = "battery_samples.jsonl"

# Approximate Li-Ion discharge curve (voltage -> state-of-charge %).
BATTERY_SOC_CURVE = [
    (4.20, 100.0),
    (4.15, 98.0),
    (4.12, 95.0),
    (4.10, 93.0),
    (4.05, 90.0),
    (4.00, 80.0),
    (3.95, 72.0),
    (3.92, 65.0),
    (3.90, 60.0),
    (3.87, 55.0),
    (3.84, 50.0),
    (3.80, 45.0),
    (3.78, 40.0),
    (3.75, 35.0),
    (3.72, 30.0),
    (3.70, 27.0),
    (3.68, 24.0),
    (3.65, 20.0),
    (3.60, 15.0),
    (3.55, 10.0),
    (3.50, 6.0),
    (3.45, 3.0),
    (3.40, 1.0),
    (3.35, 0.0),
]

FULL_VOLTAGE_THRESHOLD = 4.15
EMPTY_VOLTAGE_THRESHOLD = 3.40
MAX_DELTA_SECONDS = 600  # Ignore gaps longer than 10 minutes for coulomb counting.
MIN_CYCLE_FRACTION = 0.2  # Require at least 20% of nominal capacity to update learnt capacity.
CAPACITY_SMOOTHING = 0.3  # EWMA factor when updating learnt capacity.
MIN_CURRENT_FOR_RUNTIME_A = 0.05  # 50 mA threshold for estimating runtime.


def voltage_to_soc(voltage: float) -> float:
    """Map a voltage reading to an approximate SoC percentage."""

    curve = BATTERY_SOC_CURVE
    if voltage >= curve[0][0]:
        return 100.0
    if voltage <= curve[-1][0]:
        return 0.0
    for (v_hi, soc_hi), (v_lo, soc_lo) in zip(curve, curve[1:]):
        if v_lo <= voltage <= v_hi:
            span = v_hi - v_lo
            if span <= 0:
                return soc_lo
            fraction = (voltage - v_lo) / span
            return soc_lo + fraction * (soc_hi - soc_lo)
    return max(0.0, min(100.0, curve[-1][1]))


@dataclass
class BatteryEstimate:
    """Result returned after recording a battery sample."""

    soc_pct: float
    voltage_soc_pct: float
    coulomb_soc_pct: Optional[float]
    capacity_mah: float
    time_to_empty_hours: Optional[float]
    time_to_full_hours: Optional[float]
    samples_recorded: int


class BatteryEstimator:
    """Persist battery telemetry and learn refined capacity/runtime estimates."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / STATE_FILENAME
        self.history_path = self.data_dir / HISTORY_FILENAME
        self.state = self._load_state()

    # ------------------------------------------------------------------
    # State persistence helpers
    # ------------------------------------------------------------------

    def _load_state(self) -> Dict[str, object]:
        default = {
            "learned_capacity_mah": None,
            "soc_coulomb": None,
            "discharge_since_full_ah": 0.0,
            "charge_since_empty_ah": 0.0,
            "last_timestamp": None,
            "last_current_a": None,
            "last_flow": None,
            "samples_recorded": 0,
        }
        if not self.state_path.exists():
            return default
        try:
            loaded = json.loads(self.state_path.read_text())
        except json.JSONDecodeError:
            return default
        default.update(loaded)
        return default

    def _save_state(self) -> None:
        self.state_path.write_text(json.dumps(self.state))

    def _append_history(self, sample: Dict[str, object]) -> None:
        with self.history_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(sample) + "\n")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_sample(
        self,
        *,
        timestamp: Optional[float],
        voltage_v: float,
        current_ma: Optional[float],
        flow: str,
        nominal_capacity_mah: float,
    ) -> BatteryEstimate:
        """Record a battery telemetry sample and return updated estimates."""

        ts = timestamp if timestamp is not None else time.time()
        current_ma = float(current_ma or 0.0)
        current_a = current_ma / 1000.0

        sample = {
            "timestamp": ts,
            "voltage_v": voltage_v,
            "current_ma": current_ma,
            "flow": flow,
        }
        self._append_history(sample)

        self._update_state(ts, voltage_v, current_a, flow, nominal_capacity_mah)
        self._save_state()

        return self._build_estimate(voltage_v, current_a, flow, nominal_capacity_mah)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_state(
        self,
        timestamp: float,
        voltage_v: float,
        current_a: float,
        flow: str,
        nominal_capacity_mah: float,
    ) -> None:
        state = self.state

        learned_capacity_mah = state.get("learned_capacity_mah") or nominal_capacity_mah
        capacity_ah_ref = max(0.1, learned_capacity_mah / 1000.0)

        last_timestamp = state.get("last_timestamp")
        last_flow = state.get("last_flow")
        last_current_a = state.get("last_current_a") or 0.0

        # Coulomb counting when samples are close enough.
        if last_timestamp is not None:
            delta_seconds = timestamp - float(last_timestamp)
            if 0 < delta_seconds <= MAX_DELTA_SECONDS:
                delta_hours = delta_seconds / 3600.0
                avg_current = (abs(current_a) + abs(last_current_a)) / 2.0
                if last_flow == "discharging" and flow == "discharging":
                    discharge_ah = avg_current * delta_hours
                    state["discharge_since_full_ah"] = float(state.get("discharge_since_full_ah", 0.0)) + discharge_ah
                    if state.get("soc_coulomb") is not None:
                        state["soc_coulomb"] = max(
                            0.0,
                            float(state["soc_coulomb"]) - discharge_ah / capacity_ah_ref,
                        )
                elif last_flow == "charging" and flow == "charging":
                    charge_ah = avg_current * delta_hours
                    state["charge_since_empty_ah"] = float(state.get("charge_since_empty_ah", 0.0)) + charge_ah
                    if state.get("soc_coulomb") is not None:
                        state["soc_coulomb"] = min(
                            1.0,
                            float(state["soc_coulomb"]) + charge_ah / capacity_ah_ref,
                        )

        # Detect near-full / near-empty events to reset counters and learn capacity.
        discharge_since_full = float(state.get("discharge_since_full_ah", 0.0))
        charge_since_empty = float(state.get("charge_since_empty_ah", 0.0))
        nominal_ah = max(0.1, nominal_capacity_mah / 1000.0)
        min_cycle_ah = nominal_ah * MIN_CYCLE_FRACTION

        if flow == "charging" and voltage_v >= FULL_VOLTAGE_THRESHOLD:
            if discharge_since_full >= min_cycle_ah:
                observed_capacity_mah = discharge_since_full * 1000.0
                previous = state.get("learned_capacity_mah")
                if previous:
                    updated = (1.0 - CAPACITY_SMOOTHING) * float(previous) + CAPACITY_SMOOTHING * observed_capacity_mah
                else:
                    updated = observed_capacity_mah
                state["learned_capacity_mah"] = max(updated, nominal_capacity_mah * MIN_CYCLE_FRACTION)
            state["soc_coulomb"] = 1.0
            state["discharge_since_full_ah"] = 0.0
            state["charge_since_empty_ah"] = 0.0
        elif flow == "discharging" and voltage_v <= EMPTY_VOLTAGE_THRESHOLD:
            if charge_since_empty >= min_cycle_ah:
                observed_capacity_mah = charge_since_empty * 1000.0
                previous = state.get("learned_capacity_mah")
                if previous:
                    updated = (1.0 - CAPACITY_SMOOTHING) * float(previous) + CAPACITY_SMOOTHING * observed_capacity_mah
                else:
                    updated = observed_capacity_mah
                state["learned_capacity_mah"] = max(updated, nominal_capacity_mah * MIN_CYCLE_FRACTION)
            state["soc_coulomb"] = 0.0
            state["charge_since_empty_ah"] = 0.0

        # Initialise coulomb counter when encountering obvious full charge.
        if state.get("soc_coulomb") is None:
            if voltage_v >= FULL_VOLTAGE_THRESHOLD and flow == "charging":
                state["soc_coulomb"] = 1.0
            elif voltage_v <= EMPTY_VOLTAGE_THRESHOLD and flow == "discharging":
                state["soc_coulomb"] = 0.0

        state["last_timestamp"] = timestamp
        state["last_current_a"] = current_a
        state["last_flow"] = flow
        state["samples_recorded"] = int(state.get("samples_recorded", 0)) + 1

    def _build_estimate(
        self,
        voltage_v: float,
        current_a: float,
        flow: str,
        nominal_capacity_mah: float,
    ) -> BatteryEstimate:
        state = self.state
        learned_capacity = float(state.get("learned_capacity_mah") or nominal_capacity_mah)
        voltage_soc = voltage_to_soc(voltage_v)
        coulomb_soc = state.get("soc_coulomb")
        if coulomb_soc is not None:
            blended_soc = (voltage_soc + coulomb_soc * 100.0) / 2.0
        else:
            blended_soc = voltage_soc
        blended_soc = max(0.0, min(100.0, blended_soc))

        # Runtime estimates.
        time_to_empty = None
        time_to_full = None
        if flow == "discharging" and abs(current_a) >= MIN_CURRENT_FOR_RUNTIME_A:
            available_ah = (learned_capacity / 1000.0) * (blended_soc / 100.0)
            if available_ah > 0:
                time_to_empty = available_ah / abs(current_a)
        elif flow == "charging" and current_a >= MIN_CURRENT_FOR_RUNTIME_A:
            remaining_ah = (learned_capacity / 1000.0) * max(0.0, 1.0 - blended_soc / 100.0)
            if remaining_ah > 0:
                time_to_full = remaining_ah / current_a

        return BatteryEstimate(
            soc_pct=blended_soc,
            voltage_soc_pct=voltage_soc,
            coulomb_soc_pct=None if coulomb_soc is None else coulomb_soc * 100.0,
            capacity_mah=learned_capacity,
            time_to_empty_hours=None if time_to_empty is None else float(time_to_empty),
            time_to_full_hours=None if time_to_full is None else float(time_to_full),
            samples_recorded=int(state.get("samples_recorded", 0)),
        )
