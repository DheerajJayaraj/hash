import pytest

from dac_sim.roller_comparison import compare_roller_options


def run_comparison(**overrides):
    parameters = {
        "outer_diameter_m": 0.15,
        "face_width_m": 0.22,
        "wall_thickness_m": 0.01,
        "initial_temperature_k": 298.15,
        "target_temperature_k": 378.15,
        "heater_power_w": 500.0,
    }
    parameters.update(overrides)
    return compare_roller_options(**parameters)


def test_returns_three_roller_configurations():
    results = run_comparison()
    assert [item["configuration"] for item in results] == [
        "solid",
        "hollow",
        "hollow_with_static_fluid",
    ]


def test_hollow_shell_has_less_metal_than_solid_roller():
    solid, hollow, _ = run_comparison()
    assert hollow["metal_mass_kg"] < solid["metal_mass_kg"]


def test_static_fluid_increases_heat_capacity():
    _, hollow, fluid_filled = run_comparison()
    assert fluid_filled["heat_capacity_j_k"] > hollow["heat_capacity_j_k"]


def test_heating_energy_matches_heat_capacity():
    results = run_comparison()
    for result in results:
        assert result["ideal_heating_energy_j"] == pytest.approx(
            result["heat_capacity_j_k"] * 80.0
        )


def test_heating_time_matches_ideal_energy_balance():
    results = run_comparison()
    for result in results:
        assert result["ideal_heating_time_s"] == pytest.approx(
            result["ideal_heating_energy_j"] / 500.0
        )


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("outer_diameter_m", 0.0),
        ("face_width_m", -0.1),
        ("wall_thickness_m", 0.08),
        ("heater_power_w", 0.0),
        ("fluid_fill_fraction", 1.1),
    ],
)
def test_invalid_parameters_are_rejected(override, value):
    with pytest.raises(ValueError):
        run_comparison(**{override: value})


def test_target_below_initial_temperature_is_rejected():
    with pytest.raises(ValueError):
        run_comparison(
            initial_temperature_k=378.15,
            target_temperature_k=298.15,
        )
