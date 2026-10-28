"""Tests for the M0 assumptions loader and validator."""

from pathlib import Path

import pytest

from dac_sim.assumptions import get_value, load_assumptions
from dac_sim.validation import (
    AssumptionValidationError,
    validate_register,
)

ROOT = Path(__file__).resolve().parents[1]
ASSUMPTIONS_FILE = ROOT / "assumptions.yaml"


def valid_entry(value=1.0, unit="K", bounds=None):
    return {
        "value": value,
        "unit": unit,
        "tag": "ASSUMED",
        "source": "test fixture",
        "range": bounds,
    }


def test_baseline_register_loads():
    register = load_assumptions(ASSUMPTIONS_FILE)
    assert register["project"]["uptake_rate"]["value"] == pytest.approx(0.065)


def test_prototype_inputs_are_present():
    register = load_assumptions(ASSUMPTIONS_FILE)
    prototype = get_value(register, "prototype")
    assert prototype["exposed_area"] == pytest.approx(0.054)
    assert prototype["nominal_loop_length"] == pytest.approx(1.98)


def test_all_entries_have_required_metadata():
    register = load_assumptions(ASSUMPTIONS_FILE)
    for entry in register["project"].values():
        assert set(("value", "unit", "tag", "source", "range")) <= set(entry)


def test_invalid_tag_is_rejected():
    data = {"project": {"x": valid_entry()}}
    data["project"]["x"]["tag"] = "GUESSED"
    with pytest.raises(AssumptionValidationError, match="provenance tag"):
        validate_register(data)


def test_out_of_range_value_is_rejected():
    data = {"project": {"x": valid_entry(5.0, "K", [0.0, 2.0])}}
    with pytest.raises(AssumptionValidationError, match="outside permitted range"):
        validate_register(data)


def test_missing_metadata_is_rejected():
    data = {"project": {"x": {"value": 1, "unit": "K"}}}
    with pytest.raises(AssumptionValidationError, match="missing required field"):
        validate_register(data)


def test_invalid_range_is_rejected():
    data = {"project": {"x": valid_entry(1.0, "K", [2.0, 0.0])}}
    with pytest.raises(AssumptionValidationError, match="minimum exceeds maximum"):
        validate_register(data)


def test_yaml_root_must_be_mapping():
    with pytest.raises(AssumptionValidationError, match="root must be a mapping"):
        validate_register(["not", "a", "mapping"])


def test_unknown_unit_is_rejected():
    data = {"project": {"x": valid_entry(1.0, "imaginary_unit")}}
    with pytest.raises(AssumptionValidationError, match="unsupported unit"):
        validate_register(data)


def test_nested_prototype_values_are_checked():
    register = load_assumptions(ASSUMPTIONS_FILE)
    register["project"]["prototype"]["value"]["belt_width"] = float("nan")
    with pytest.raises(AssumptionValidationError, match="finite numeric value"):
        validate_register(register)


def test_nested_unit_mapping_must_match_values():
    register = load_assumptions(ASSUMPTIONS_FILE)
    register["project"]["geometry_units"]["value"].pop("belt_width")
    with pytest.raises(AssumptionValidationError, match="keys must match"):
        validate_register(register)


def test_numeric_boolean_is_rejected():
    data = {"project": {"x": valid_entry(True, "K", [0.0, 2.0])}}
    with pytest.raises(AssumptionValidationError, match="finite numeric value"):
        validate_register(data)
# M0 physical-consistency regression tests


def test_exposed_area_must_match_geometry():
    register = load_assumptions(ASSUMPTIONS_FILE)
    register["project"]["prototype"]["value"]["exposed_area"] = 0.08
    with pytest.raises(AssumptionValidationError, match="exposed_area"):
        validate_register(register)


def test_nominal_sorbent_mass_must_match_geometry():
    register = load_assumptions(ASSUMPTIONS_FILE)
    register["project"]["prototype"]["value"]["nominal_sorbent_mass"] = 0.2
    with pytest.raises(AssumptionValidationError, match="nominal_sorbent_mass"):
        validate_register(register)


def test_capture_rate_must_match_uptake_and_exposed_mass():
    register = load_assumptions(ASSUMPTIONS_FILE)
    register["project"]["prototype"]["value"]["expected_capture_rate"] = 0.01
    with pytest.raises(AssumptionValidationError, match="expected_capture_rate"):
        validate_register(register)


def test_nominal_belt_speed_must_be_within_range():
    register = load_assumptions(ASSUMPTIONS_FILE)
    register["project"]["prototype"]["value"]["nominal_belt_speed"] = 0.01
    with pytest.raises(AssumptionValidationError, match="nominal belt speed"):
        validate_register(register)


def test_usable_belt_width_must_not_exceed_total_width():
    register = load_assumptions(ASSUMPTIONS_FILE)
    register["project"]["prototype"]["value"]["usable_belt_width"] = 0.25
    with pytest.raises(AssumptionValidationError, match="usable_belt_width"):
        validate_register(register)


def test_non_finite_prototype_value_is_rejected():
    register = load_assumptions(ASSUMPTIONS_FILE)
    register["project"]["prototype"]["value"]["fan_face_area"] = float("nan")
    with pytest.raises(AssumptionValidationError, match="finite numeric value"):
        validate_register(register)


def test_wrap_angle_above_full_rotation_is_rejected():
    register = load_assumptions(ASSUMPTIONS_FILE)
    register["project"]["prototype"]["value"]["hot_roller_wrap_angle"] = 7.0
    with pytest.raises(AssumptionValidationError, match="wrap angles"):
        validate_register(register)


def test_zero_wrap_angle_is_rejected():
    register = load_assumptions(ASSUMPTIONS_FILE)
    register["project"]["prototype"]["value"]["intermediate_wrap_angle"] = 0.0
    with pytest.raises(AssumptionValidationError, match="greater than zero"):
        validate_register(register)
def test_capture_rate_assumptions_use_expected_units():
    register = load_assumptions(ASSUMPTIONS_FILE)
    project = register["project"]
    prototype = project["prototype"]["value"]
    units = project["geometry_units"]["value"]

    assert project["uptake_rate"]["unit"] == "mmol/g/min"
    assert units["exposed_sorbent_mass"] == "kg"
    assert units["expected_capture_rate"] == "kg/h"
    assert prototype["expected_capture_rate"] == pytest.approx(0.0028)
    validate_register(register)


def test_capture_rate_accepts_consistent_mmol_to_kg_conversion():
    register = load_assumptions(ASSUMPTIONS_FILE)
    project = register["project"]
    prototype = project["prototype"]["value"]

    uptake_mmol_g_min = project["uptake_rate"]["value"]
    exposed_mass_kg = prototype["exposed_sorbent_mass"]

    # Convert mmol/g/min to kg CO2/h using 44.01 g/mol CO2.
    calculated_capture_kg_h = (
        uptake_mmol_g_min
        * exposed_mass_kg
        * 1000.0
        * 44.01
        * 60.0
        / 1_000_000.0
    )

    prototype["expected_capture_rate"] = calculated_capture_kg_h
    validate_register(register)
