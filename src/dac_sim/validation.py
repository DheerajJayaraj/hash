"""Validation helpers for the DAC assumptions register."""

from __future__ import annotations

import math
from typing import Any

VALID_TAGS = {"MEASURED", "PUBLISHED", "ASSUMED"}

VALID_UNITS = {
    "text", "mapping", "dimensionless", "percent",
    "K", "degC", "?C", "C",
    "m", "mm", "cm", "m2", "m3", "m/s", "mm/s", "m2/s", "m3/s",
    "rad", "s", "min", "h", "rpm",
    "W", "kW", "J", "kJ", "kWh", "Pa", "kPa",
    "W/K", "W/m/K", "W/m2/K", "W/m2",
    "kg", "g", "mg", "kg/s", "kg/h", "kg/m2", "kg/m3",
    "g/m3", "g/mol", "mol", "mmol", "mol/s", "mol/m2/s",
    "mmol/g", "mmol/g/min", "L/min", "m3/h",
    "MWh/t_CO2", "MWh/t_methanol", "t_CO2/t_methanol",
}

UNIT_MAP_NAMES = {"geometry_units", "scale_up_units", "regression_units"}
NESTED_PARAMETER_UNITS = {
    "prototype": "geometry_units",
    "scale_up": "scale_up_units",
    "regression_targets": "regression_units",
}


class AssumptionValidationError(ValueError):
    """Raised when an assumption is missing or invalid."""


def _finite_number(value: Any) -> bool:
    """Return True for finite numeric values, excluding booleans."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_register(data: Any) -> None:
    """Validate metadata, units, numeric ranges, and nested parameters."""
    if not isinstance(data, dict):
        raise AssumptionValidationError("Register root must be a mapping.")

    parameters = data.get("project")
    if not isinstance(parameters, dict) or not parameters:
        raise AssumptionValidationError(
            "Register must contain a non-empty 'project' mapping."
        )

    # Validate common metadata and scalar values first.
    for name, entry in parameters.items():
        if not isinstance(entry, dict):
            raise AssumptionValidationError(
                f"{name}: each parameter must be a mapping."
            )

        for key in ("value", "unit", "tag", "source", "range"):
            if key not in entry:
                raise AssumptionValidationError(
                    f"{name}: missing required field '{key}'."
                )

        unit = entry["unit"]
        if not isinstance(unit, str) or unit not in VALID_UNITS:
            raise AssumptionValidationError(
                f"{name}: unsupported unit {unit!r}."
            )

        if entry["tag"] not in VALID_TAGS:
            raise AssumptionValidationError(
                f"{name}: invalid provenance tag {entry['tag']!r}."
            )

        if not isinstance(entry["source"], str) or not entry["source"].strip():
            raise AssumptionValidationError(
                f"{name}: source must be non-empty."
            )

        value = entry["value"]
        bounds = entry["range"]

        if bounds is not None:
            if (
                not isinstance(bounds, list)
                or len(bounds) != 2
                or not all(_finite_number(bound) for bound in bounds)
            ):
                raise AssumptionValidationError(
                    f"{name}: range must be null or [finite_min, finite_max]."
                )

            lower, upper = bounds
            if lower > upper:
                raise AssumptionValidationError(
                    f"{name}: range minimum exceeds maximum."
                )

            if not _finite_number(value):
                raise AssumptionValidationError(
                    f"{name}: numeric range requires a finite numeric value."
                )

            if not lower <= value <= upper:
                raise AssumptionValidationError(
                    f"{name}: value {value} outside permitted range "
                    f"[{lower}, {upper}]."
                )

        if isinstance(value, float) and not math.isfinite(value):
            raise AssumptionValidationError(
                f"{name}: value must be finite."
            )

    # Validate unit maps separately from structured numeric records.
    for name in UNIT_MAP_NAMES:
        entry = parameters.get(name)
        if not isinstance(entry, dict):
            raise AssumptionValidationError(
                f"Missing required unit mapping '{name}'."
            )

        units = entry["value"]
        if not isinstance(units, dict):
            raise AssumptionValidationError(
                f"{name}: value must be a mapping."
            )

        for field, unit in units.items():
            if not isinstance(unit, str) or unit not in VALID_UNITS:
                raise AssumptionValidationError(
                    f"{name}.{field}: unsupported unit {unit!r}."
                )

    # Validate each nested numeric record against its matching unit map.
    for name, unit_map_name in NESTED_PARAMETER_UNITS.items():
        entry = parameters.get(name)
        if not isinstance(entry, dict) or not isinstance(entry["value"], dict):
            raise AssumptionValidationError(
                f"{name}: expected a mapping of numeric values."
            )

        values = entry["value"]
        units = parameters[unit_map_name]["value"]

        if set(values) != set(units):
            raise AssumptionValidationError(
                f"{name}: values and {unit_map_name} keys must match."
            )

        for field, value in values.items():
            if not _finite_number(value):
                raise AssumptionValidationError(
                    f"{name}.{field}: expected a finite numeric value."
                )
