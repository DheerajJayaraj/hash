import pytest

from dac_sim.fluid_loop import fluid_wall_step


def step(**overrides):
    parameters = {
        "wall_temperature_k": 350.0,
        "wall_mass_kg": 2.0,
        "wall_specific_heat_j_kg_k": 500.0,
        "fluid_temperature_k": 330.0,
        "fluid_mass_kg": 1.0,
        "fluid_specific_heat_j_kg_k": 4180.0,
        "fluid_inlet_temperature_k": 330.0,
        "mass_flow_rate_kg_s": 0.01,
        "wall_fluid_conductance_w_k": 10.0,
        "heater_power_w": 0.0,
        "ambient_temperature_k": 298.15,
        "wall_ambient_conductance_w_k": 0.0,
        "time_step_s": 0.1,
    }
    parameters.update(overrides)
    return fluid_wall_step(**parameters)


def test_hot_wall_heats_cooler_fluid():
    result = step()
    assert result["wall_temperature_k"] < 350.0
    assert result["fluid_temperature_k"] > 330.0


def test_heater_increases_wall_temperature():
    unheated = step()
    heated = step(heater_power_w=100.0)
    assert heated["wall_temperature_k"] > unheated["wall_temperature_k"]


def test_no_link_no_flow_no_heater_keeps_temperatures():
    result = step(
        wall_fluid_conductance_w_k=0.0,
        mass_flow_rate_kg_s=0.0,
    )
    assert result["wall_temperature_k"] == pytest.approx(350.0)
    assert result["fluid_temperature_k"] == pytest.approx(330.0)


def test_energy_balance_includes_flow_and_ambient():
    result = step()
    wall_energy_change = 2.0 * 500.0 * (
        result["wall_temperature_k"] - 350.0
    )
    fluid_energy_change = 1.0 * 4180.0 * (
        result["fluid_temperature_k"] - 330.0
    )
    expected_energy_change = (
        result["wall_net_heat_rate_w"]
        + result["fluid_net_heat_rate_w"]
    ) * 0.1

    assert wall_energy_change + fluid_energy_change == pytest.approx(
        expected_energy_change,
        abs=1e-9,
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("wall_mass_kg", 0.0),
        ("fluid_mass_kg", -1.0),
        ("mass_flow_rate_kg_s", -0.1),
        ("wall_fluid_conductance_w_k", -1.0),
        ("time_step_s", 0.0),
        ("ambient_temperature_k", 0.0),
    ],
)
def test_invalid_parameters_are_rejected(key, value):
    with pytest.raises(ValueError):
        step(**{key: value})


def test_large_time_step_is_rejected():
    with pytest.raises(ValueError, match="Time step is too large"):
        step(time_step_s=1000.0)


def test_energy_balance_with_ambient_exchange():
    result = step(
        wall_ambient_conductance_w_k=2.0,
        ambient_temperature_k=298.15,
        fluid_inlet_temperature_k=340.0,
    )

    wall_energy_change = 2.0 * 500.0 * (
        result["wall_temperature_k"] - 350.0
    )
    fluid_energy_change = 1.0 * 4180.0 * (
        result["fluid_temperature_k"] - 330.0
    )
    expected_energy_change = (
        result["wall_net_heat_rate_w"]
        + result["fluid_net_heat_rate_w"]
    ) * 0.1

    assert wall_energy_change + fluid_energy_change == pytest.approx(
        expected_energy_change,
        abs=1e-9,
    )
    assert result["ambient_heat_rate_w"] < 0


def test_coupled_wall_fluid_energy_is_conserved_over_many_steps():
    wall_temperature = 350.0
    fluid_temperature = 300.0

    initial_energy = (
        2.0 * 500.0 * wall_temperature
        + 1.0 * 4180.0 * fluid_temperature
    )

    for _ in range(1000):
        result = fluid_wall_step(
            wall_temperature_k=wall_temperature,
            wall_mass_kg=2.0,
            wall_specific_heat_j_kg_k=500.0,
            fluid_temperature_k=fluid_temperature,
            fluid_mass_kg=1.0,
            fluid_specific_heat_j_kg_k=4180.0,
            fluid_inlet_temperature_k=300.0,
            mass_flow_rate_kg_s=0.0,
            wall_fluid_conductance_w_k=10.0,
            heater_power_w=0.0,
            ambient_temperature_k=300.0,
            wall_ambient_conductance_w_k=0.0,
            time_step_s=0.1,
        )
        wall_temperature = result["wall_temperature_k"]
        fluid_temperature = result["fluid_temperature_k"]

    final_energy = (
        2.0 * 500.0 * wall_temperature
        + 1.0 * 4180.0 * fluid_temperature
    )

    assert final_energy == pytest.approx(initial_energy, abs=1e-7)
    assert 300.0 < fluid_temperature < wall_temperature < 350.0


def test_coupled_wall_fluid_temperatures_approach_equilibrium():
    wall_temperature = 350.0
    fluid_temperature = 300.0

    initial_difference = abs(wall_temperature - fluid_temperature)

    for _ in range(1000):
        result = fluid_wall_step(
            wall_temperature_k=wall_temperature,
            wall_mass_kg=2.0,
            wall_specific_heat_j_kg_k=500.0,
            fluid_temperature_k=fluid_temperature,
            fluid_mass_kg=1.0,
            fluid_specific_heat_j_kg_k=4180.0,
            fluid_inlet_temperature_k=300.0,
            mass_flow_rate_kg_s=0.0,
            wall_fluid_conductance_w_k=10.0,
            heater_power_w=0.0,
            ambient_temperature_k=300.0,
            wall_ambient_conductance_w_k=0.0,
            time_step_s=0.1,
        )
        wall_temperature = result["wall_temperature_k"]
        fluid_temperature = result["fluid_temperature_k"]

    final_difference = abs(wall_temperature - fluid_temperature)

    assert final_difference < initial_difference
    assert wall_temperature > fluid_temperature
    assert wall_temperature > 300.0
    assert fluid_temperature > 300.0


def test_coupled_stability_guard_rejects_large_time_step():
    with pytest.raises(
        ValueError,
        match="stable coupled-system integration",
    ):
        fluid_wall_step(
            wall_temperature_k=350.0,
            wall_mass_kg=2.0,
            wall_specific_heat_j_kg_k=500.0,
            fluid_temperature_k=300.0,
            fluid_mass_kg=1.0,
            fluid_specific_heat_j_kg_k=4180.0,
            fluid_inlet_temperature_k=300.0,
            mass_flow_rate_kg_s=0.0,
            wall_fluid_conductance_w_k=10.0,
            heater_power_w=0.0,
            ambient_temperature_k=300.0,
            wall_ambient_conductance_w_k=0.0,
            time_step_s=90.0,
        )
