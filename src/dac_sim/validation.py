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


def _require(condition: bool, message: str) -> None:
    """Raise a consistent error for a failed physical-consistency check."""
    if not condition:
        raise AssumptionValidationError(message)


def _close(actual: float, expected: float, relative_tolerance: float) -> bool:
    """Compare positive physical quantities with an explicit relative tolerance."""
    return math.isclose(
        actual,
        expected,
        rel_tol=relative_tolerance,
        abs_tol=1e-12,
    )


def _validate_physical_consistency(parameters: dict[str, Any]) -> None:
    """Check internal physical consistency for the complete project register."""
    prototype = parameters["prototype"]["value"]

    # Strictly positive dimensions and operating quantities.
    positive_fields = (
        "belt_width",
        "usable_belt_width",
        "belt_thickness_min",
        "belt_thickness_max",
        "nominal_loop_length",
        "end_roller_diameter",
        "end_roller_face_width",
        "intermediate_roller_diameter",
        "roller_spacing",
        "wall_thickness",
        "slot_height",
        "slot_width",
        "exposed_length",
        "exposed_area",
        "fan_face_area",
        "hot_roller_wrap_angle",
        "intermediate_wrap_angle",
        "heater_power",
        "loop_flow_min",
        "loop_flow_max",
        "fan_flow_min",
        "fan_flow_max",
        "fan_pressure_min",
        "fan_pressure_max",
        "belt_speed_min",
        "belt_speed_max",
        "nominal_belt_speed",
        "nominal_sorbent_mass",
        "exposed_sorbent_mass",
        "expected_capture_rate",
    )
    for field in positive_fields:
        _require(
            _finite_number(prototype[field]) and prototype[field] > 0,
            f"prototype.{field}: must be a finite number greater than zero.",
        )

    _require(
        prototype["usable_belt_width"] <= prototype["belt_width"],
        "prototype.usable_belt_width must not exceed belt_width.",
    )
    _require(
        prototype["belt_thickness_min"] <= prototype["belt_thickness_max"],
        "prototype belt thickness minimum must not exceed maximum.",
    )
    _require(
        prototype["loop_flow_min"] <= prototype["loop_flow_max"],
        "prototype loop flow minimum must not exceed maximum.",
    )
    _require(
        prototype["fan_flow_min"] <= prototype["fan_flow_max"],
        "prototype fan flow minimum must not exceed maximum.",
    )
    _require(
        prototype["fan_pressure_min"] <= prototype["fan_pressure_max"],
        "prototype fan pressure minimum must not exceed maximum.",
    )
    _require(
        prototype["belt_speed_min"]
        <= prototype["nominal_belt_speed"]
        <= prototype["belt_speed_max"],
        "prototype nominal belt speed must lie within its configured range.",
    )
    _require(
        0 < prototype["hot_roller_wrap_angle"] <= 2 * math.pi
        and 0 < prototype["intermediate_wrap_angle"] <= 2 * math.pi,
        "prototype wrap angles must be greater than zero and at most 2*pi radians.",
    )

    # Geometry: exposed area = exposed belt length * usable belt width.
    expected_exposed_area = (
        prototype["exposed_length"] * prototype["usable_belt_width"]
    )
    _require(
        _close(prototype["exposed_area"], expected_exposed_area, 0.01),
        "prototype.exposed_area is inconsistent with exposed_length "
        "times usable_belt_width (1% tolerance).",
    )

    # Sorbent mass = loop length * usable width * sorbent areal loading.
    areal_loading = parameters["sorbent_areal_loading"]["value"]
    _require(
        _finite_number(areal_loading) and areal_loading > 0,
        "sorbent_areal_loading must be a positive finite number.",
    )
    expected_nominal_mass = (
        prototype["nominal_loop_length"]
        * prototype["usable_belt_width"]
        * areal_loading
    )
    _require(
        _close(prototype["nominal_sorbent_mass"], expected_nominal_mass, 0.02),
        "prototype.nominal_sorbent_mass is inconsistent with loop geometry "
        "and sorbent_areal_loading (2% tolerance).",
    )

    # Capture estimate: uptake [mmol/g/min] * sorbent [g] *
    # 44.01 [mg/mmol] * 60 [min/h] / 1e6 [mg/kg] = kg CO2/h.
    uptake_rate = parameters["uptake_rate"]["value"]
    _require(
        _finite_number(uptake_rate) and uptake_rate > 0,
        "uptake_rate must be a positive finite number.",
    )
    expected_capture_rate = (
        uptake_rate
        * prototype["exposed_sorbent_mass"]
        * 1000.0
        * 44.01
        * 60.0
        / 1_000_000.0
    )
    _require(
        _close(prototype["expected_capture_rate"], expected_capture_rate, 0.05),
        "prototype.expected_capture_rate is inconsistent with uptake_rate "
        "and exposed_sorbent_mass (5% tolerance).",
    )


def validate_register(data: Any) -> None:
    """Validate metadata, units, numeric ranges, nested values, and physics checks."""
    if not isinstance(data, dict):
        raise AssumptionValidationError("Register root must be a mapping.")

    parameters = data.get("project")
    if not isinstance(parameters, dict) or not parameters:
        raise AssumptionValidationError(
            "Register must contain a non-empty 'project' mapping."
        )

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

    for name in UNIT_MAP_NAMES:
        entry = parameters.get(name)
        if not isinstance(entry, dict):
            raise AssumptionValidationError(
                f"Missing required unit mapping '{name}'."
            )

        units = entry.get("value")
        if not isinstance(units, dict):
            raise AssumptionValidationError(
                f"{name}: value must be a mapping."
            )

        for field, unit in units.items():
            if not isinstance(unit, str) or unit not in VALID_UNITS:
                raise AssumptionValidationError(
                    f"{name}.{field}: unsupported unit {unit!r}."
                )

    for name, unit_map_name in NESTED_PARAMETER_UNITS.items():
        entry = parameters.get(name)
        if not isinstance(entry, dict) or not isinstance(entry.get("value"), dict):
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

    # Apply physics checks only after the complete register has passed schema checks.
    _validate_physical_consistency(parameters)
