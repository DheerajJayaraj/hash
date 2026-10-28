"""Tests for coupled thermal network and fluid-loop simulation."""

import pytest
import yaml
from pathlib import Path

from dac_sim.fluid_loop import FluidLoop
from dac_sim.thermal import ThermalNode, ThermalLink, thermal_network_step
from dac_sim.simulation import run_thermal_simulation
from dac_sim.prototype import build_prototype_network, build_prototype_fluid_loop
from dac_sim.reporting import build_energy_report


def test_fluid_loop_dataclass_validation():
    # Valid
    loop = FluidLoop("node1", 0.01, 4180.0, 300.0)
    assert loop.node_name == "node1"
    assert loop.flow_conductance_w_k == pytest.approx(41.8)

    # Inflow warms colder node
    assert loop.heat_rate_to_node_w(290.0) == pytest.approx(41.8 * 10.0)
    # Inflow cools warmer node (heat recovery)
    assert loop.heat_rate_to_node_w(310.0) == pytest.approx(-41.8 * 10.0)

    # Rejection of invalid inputs
    with pytest.raises(ValueError, match="node_name"):
        FluidLoop("", 0.01, 4180.0, 300.0)
    with pytest.raises(ValueError, match="mass_flow_rate_kg_s"):
        FluidLoop("node1", -0.01, 4180.0, 300.0)
    with pytest.raises(ValueError, match="fluid_specific_heat"):
        FluidLoop("node1", 0.01, 0.0, 300.0)
    with pytest.raises(ValueError, match="inlet_temperature_k"):
        FluidLoop("node1", 0.01, 4180.0, -10.0)
    with pytest.raises(ValueError, match="node_temperature_k"):
        loop.heat_rate_to_node_w(-5.0)


def test_thermal_network_step_with_fluid_cooling():
    # Warm node at 350 K, fluid inlet at 300 K
    node = ThermalNode("loop", 350.0, 1.0, 4180.0)
    fluid = FluidLoop("loop", 0.02, 4180.0, 300.0)

    next_nodes = thermal_network_step(
        nodes=[node],
        links=[],
        time_step_s=0.1,
        fluid_loops=[fluid],
    )
    # Fluid must cool the node
    assert next_nodes[0].temperature_k < 350.0
    # Heat rate is 0.02 * 4180 * (300 - 350) = -4180 W
    # Temperature change in 0.1 s: -4180 * 0.1 / 4180 = -0.1 K
    assert next_nodes[0].temperature_k == pytest.approx(349.9)


def test_thermal_network_step_rejects_unknown_fluid_node():
    node = ThermalNode("loop", 350.0, 1.0, 4180.0)
    fluid = FluidLoop("nonexistent", 0.02, 4180.0, 300.0)

    with pytest.raises(ValueError, match="Fluid loop references unknown node"):
        thermal_network_step([node], [], 0.1, fluid_loops=[fluid])


def test_coupled_simulation_energy_conservation():
    # Hot roller (heated), belt (in between), and intermediate loop (cooled by fluid)
    hot_roller = ThermalNode("hot", 350.0, 2.0, 500.0)
    belt = ThermalNode("belt", 320.0, 0.5, 1000.0)
    fluid_node = ThermalNode("fluid_roller", 310.0, 1.0, 4180.0)

    nodes = [hot_roller, belt, fluid_node]
    links = [
        ThermalLink("hot", "belt", 10.0),
        ThermalLink("belt", "fluid_roller", 8.0),
    ]

    fluid = FluidLoop(
        node_name="fluid_roller",
        mass_flow_rate_kg_s=0.01,
        fluid_specific_heat_j_kg_k=4180.0,
        inlet_temperature_k=295.0,  # Cooler fluid extracts heat
    )

    external_heat = {"hot": 200.0}
    ambient_loss = {"hot": 1.0, "belt": 0.5, "fluid_roller": 1.0}

    result = run_thermal_simulation(
        nodes=nodes,
        links=links,
        duration_s=20.0,
        time_step_s=0.05,
        external_heat_w=external_heat,
        ambient_temperature_k=298.15,
        ambient_loss_conductance_w_k=ambient_loss,
        fluid_loops=[fluid],
    )

    # Check that energy balances exactly
    assert result["energy_balance_error_j"] == pytest.approx(0.0, abs=1e-8)
    assert result["fluid_energy_j"] < 0.0  # Net heat removed by fluid
    assert result["fluid_heat_recovered_j"] > 0.0  # Heat recovered
    assert result["external_energy_j"] == pytest.approx(200.0 * 20.0)

    # Build report
    report = build_energy_report(result)
    assert report["fluid_energy_j"] == pytest.approx(result["fluid_energy_j"])
    assert report["fluid_heat_recovered_j"] == pytest.approx(result["fluid_heat_recovered_j"])
    assert report["energy_balance_error_j"] == pytest.approx(0.0, abs=1e-8)


def test_coupled_stability_guard_accounts_for_fluid_flow():
    # If mass flow is very high, G_flow is huge, requiring small time step
    node = ThermalNode("small_node", 300.0, 0.01, 1000.0)  # C = 10 J/K
    # G_flow = 1.0 * 1000 = 1000 W/K -> tau = 10 / 1000 = 0.01 s
    fluid = FluidLoop("small_node", 1.0, 1000.0, 300.0)

    # dt = 0.05 s > 0.01 s -> must raise ValueError
    with pytest.raises(ValueError, match="Time step is too large"):
        thermal_network_step([node], [], time_step_s=0.05, fluid_loops=[fluid])

    # dt = 0.005 s < 0.01 s -> must succeed
    next_nodes = thermal_network_step(
        [node], [], time_step_s=0.005, fluid_loops=[fluid]
    )
    assert len(next_nodes) == 1


def test_build_prototype_fluid_loop_from_assumptions():
    assumptions_path = Path("assumptions.yaml")
    with assumptions_path.open(encoding="utf-8-sig") as f:
        data = yaml.safe_load(f)

    # Default build
    loop = build_prototype_fluid_loop(data)
    assert loop.node_name == "intermediate_loop"
    assert loop.inlet_temperature_k == pytest.approx(338.15)
    # Default flow is 0.5 L/min -> 0.5 * 1.0 / 60 = 0.008333 kg/s
    assert loop.mass_flow_rate_kg_s == pytest.approx(0.5 / 60.0)

    # Custom flow rate override
    custom_loop = build_prototype_fluid_loop(
        data, flow_rate_l_min=1.0, inlet_temperature_k=300.0
    )
    assert custom_loop.mass_flow_rate_kg_s == pytest.approx(1.0 / 60.0)
    assert custom_loop.inlet_temperature_k == pytest.approx(300.0)

    # Negative flow rejection
    with pytest.raises(ValueError, match="flow_rate_l_min"):
        build_prototype_fluid_loop(data, flow_rate_l_min=-0.5)
