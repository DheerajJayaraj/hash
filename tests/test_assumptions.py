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
