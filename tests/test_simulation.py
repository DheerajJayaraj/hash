import pytest

from dac_sim.simulation import run_thermal_simulation
from dac_sim.thermal import ThermalNode, ThermalLink


def test_simulation_reaches_exact_requested_duration():
    nodes = [ThermalNode("node", 300.0, 1.0, 1000.0)]
    result = run_thermal_simulation(nodes, [], 1.05, 0.2)

    assert result["time_s"][-1] == pytest.approx(1.05)
    assert result["time_s"][0] == pytest.approx(0.0)


def test_simulation_accounts_for_external_energy():
    nodes = [ThermalNode("node", 300.0, 1.0, 1000.0)]
    result = run_thermal_simulation(
        nodes, [], 10.0, 0.3, {"node": 100.0}
    )

    assert result["external_energy_j"] == pytest.approx(1000.0)
    assert result["total_internal_energy_change_j"] == pytest.approx(1000.0)
    assert result["energy_balance_error_j"] == pytest.approx(0.0, abs=1e-9)


def test_simulation_conserves_energy_between_two_nodes():
    nodes = [
        ThermalNode("hot", 350.0, 2.0, 500.0),
        ThermalNode("cold", 300.0, 1.0, 1000.0),
    ]
    links = [ThermalLink("hot", "cold", 10.0)]

    result = run_thermal_simulation(nodes, links, 1.0, 0.01)

    assert result["external_energy_j"] == pytest.approx(0.0)
    assert result["energy_balance_error_j"] == pytest.approx(0.0, abs=1e-8)


def test_simulation_records_each_node_temperature():
    nodes = [
        ThermalNode("hot", 350.0, 2.0, 500.0),
        ThermalNode("cold", 300.0, 1.0, 1000.0),
    ]
    result = run_thermal_simulation(
        nodes, [ThermalLink("hot", "cold", 10.0)], 1.0, 0.1
    )

    assert len(result["temperature_history_k"]["hot"]) == len(result["time_s"])
    assert len(result["temperature_history_k"]["cold"]) == len(result["time_s"])


@pytest.mark.parametrize(
    ("duration", "step"),
    [(0.0, 0.1), (-1.0, 0.1), (1.0, 0.0), (1.0, -0.1)],
)
def test_simulation_rejects_non_positive_duration_or_step(duration, step):
    nodes = [ThermalNode("node", 300.0, 1.0, 1000.0)]

    with pytest.raises(ValueError):
        run_thermal_simulation(nodes, [], duration, step)


def test_simulation_rejects_unknown_external_heat_node():
    nodes = [ThermalNode("node", 300.0, 1.0, 1000.0)]

    with pytest.raises(ValueError, match="unknown node"):
        run_thermal_simulation(
            nodes, [], 1.0, 0.1, {"missing": 10.0}
        )


def test_simulation_accounts_for_ambient_heat_loss():
    nodes = [ThermalNode("hot", 350.0, 2.0, 500.0)]

    result = run_thermal_simulation(
        nodes, [], 10.0, 0.1,
        ambient_temperature_k=298.15,
        ambient_loss_conductance_w_k={"hot": 2.0},
    )

    assert result["ambient_energy_j"] < 0
    assert result["total_internal_energy_change_j"] < 0
    assert result["energy_balance_error_j"] == pytest.approx(0.0, abs=1e-8)


def test_simulation_accounts_for_ambient_heat_gain():
    nodes = [ThermalNode("cold", 280.0, 1.0, 1000.0)]

    result = run_thermal_simulation(
        nodes, [], 10.0, 0.1,
        ambient_temperature_k=298.15,
        ambient_loss_conductance_w_k={"cold": 2.0},
    )

    final_temperature = result["temperature_history_k"]["cold"][-1]
    assert final_temperature > 280.0
    assert result["ambient_energy_j"] > 0
    assert result["energy_balance_error_j"] == pytest.approx(0.0, abs=1e-8)


def test_simulation_combines_heater_and_ambient_exchange():
    nodes = [ThermalNode("roller", 350.0, 2.0, 500.0)]

    result = run_thermal_simulation(
        nodes, [], 5.0, 0.1,
        external_heat_w={"roller": 200.0},
        ambient_temperature_k=298.15,
        ambient_loss_conductance_w_k={"roller": 2.0},
    )

    expected_energy = (
        result["external_energy_j"] + result["ambient_energy_j"]
    )
    assert result["total_internal_energy_change_j"] == pytest.approx(
        expected_energy, abs=1e-8
    )
    assert result["energy_balance_error_j"] == pytest.approx(0.0, abs=1e-8)