"""Reporting utilities for thermal simulation results."""

from __future__ import annotations

import math
from typing import Any


def build_energy_report(result: dict[str, Any]) -> dict[str, Any]:
    """Build a concise report from a thermal simulation result."""
    required = (
        "time_s",
        "temperature_history_k",
        "external_energy_j",
        "ambient_energy_j",
        "total_internal_energy_change_j",
        "energy_balance_error_j",
    )

    missing = [key for key in required if key not in result]
    if missing:
        raise ValueError(f"Simulation result is missing fields: {missing}")

    for key in (
        "external_energy_j",
        "ambient_energy_j",
        "total_internal_energy_change_j",
        "energy_balance_error_j",
    ):
        value = result[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{key} must be a finite number.")

    times = result["time_s"]
    histories = result["temperature_history_k"]

    if not isinstance(times, list) or not times:
        raise ValueError("time_s must be a non-empty list.")
    if not isinstance(histories, dict) or not histories:
        raise ValueError("temperature_history_k must be a non-empty mapping.")

    final_temperatures = {}
    for name, values in histories.items():
        if not isinstance(values, list) or len(values) != len(times) or not values:
            raise ValueError(
                f"Temperature history for {name!r} must match time_s."
            )
        final_temperature = values[-1]
        if (
            isinstance(final_temperature, bool)
            or not isinstance(final_temperature, (int, float))
            or not math.isfinite(final_temperature)
            or final_temperature <= 0
        ):
            raise ValueError(
                f"Final temperature for {name!r} must be finite and above zero K."
            )
        final_temperatures[name] = final_temperature

    external_energy = result["external_energy_j"]
    ambient_energy = result["ambient_energy_j"]
    stored_energy_change = result["total_internal_energy_change_j"]
    balance_error = result["energy_balance_error_j"]

    return {
        "duration_s": times[-1] - times[0],
        "external_energy_j": external_energy,
        "ambient_energy_j": ambient_energy,
        "total_energy_input_j": external_energy + ambient_energy,
        "stored_energy_change_j": stored_energy_change,
        "energy_balance_error_j": balance_error,
        "final_temperatures_k": final_temperatures,
    }
