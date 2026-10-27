"""Tests for basic transient thermal calculations."""

import math

import pytest

from dac_sim.thermal import (
    sensible_energy_change_j,
    temperature_step,
)


def test_no_net_heat_leaves_temperature_unchanged():
    result = temperature_step(300.0, 2.0, 500.0, 0.0, 10.0)
    assert result == pytest.approx(300.0)


def test_positive_heat_rate_increases_temperature():
    result = temperature_step(300.0, 2.0, 500.0, 100.0, 10.0)
    assert result == pytest.approx(301.0)


def test_negative_heat_rate_decreases_temperature():
    result = temperature_step(300.0, 2.0, 500.0, -100.0, 10.0)
    assert result == pytest.approx(299.0)


def test_temperature_step_matches_energy_balance():
    initial_k = 320.0
    mass_kg = 0.5
    cp = 800.0
    power_w = 40.0
    dt_s = 5.0

    final_k = temperature_step(initial_k, mass_kg, cp, power_w, dt_s)
    stored_energy = sensible_energy_change_j(mass_kg, cp, initial_k, final_k)

    assert stored_energy == pytest.approx(power_w * dt_s)


def test_sensible_energy_is_zero_for_same_temperature():
    assert sensible_energy_change_j(2.0, 500.0, 300.0, 300.0) == pytest.approx(0.0)


def test_cooling_has_negative_sensible_energy_change():
    result = sensible_energy_change_j(2.0, 500.0, 310.0, 300.0)
    assert result == pytest.approx(-10000.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature_k": 0.0},
        {"mass_kg": 0.0},
        {"specific_heat_j_kg_k": 0.0},
        {"time_step_s": 0.0},
    ],
)
def test_invalid_positive_inputs_are_rejected(kwargs):
    arguments = {
        "temperature_k": 300.0,
        "mass_kg": 1.0,
        "specific_heat_j_kg_k": 500.0,
        "net_heat_rate_w": 0.0,
        "time_step_s": 1.0,
    }
    arguments.update(kwargs)

    with pytest.raises(ValueError):
        temperature_step(**arguments)


def test_non_finite_heat_rate_is_rejected():
    with pytest.raises(ValueError, match="finite number"):
        temperature_step(300.0, 1.0, 500.0, math.nan, 1.0)


def test_step_that_would_cross_absolute_zero_is_rejected():
    with pytest.raises(ValueError, match="above zero K"):
        temperature_step(1.0, 1.0, 1.0, -2.0, 1.0)


def test_heat_flows_from_hot_node_to_cold_node():
    from dac_sim.thermal import thermal_link_heat_rate_w

    assert thermal_link_heat_rate_w(350.0, 300.0, 10.0) == pytest.approx(500.0)
    assert thermal_link_heat_rate_w(300.0, 350.0, 10.0) == pytest.approx(-500.0)


def test_equal_temperature_nodes_transfer_no_heat():
    from dac_sim.thermal import thermal_link_heat_rate_w

    assert thermal_link_heat_rate_w(320.0, 320.0, 12.0) == pytest.approx(0.0)


def test_zero_conductance_transfers_no_heat():
    from dac_sim.thermal import thermal_link_heat_rate_w

    assert thermal_link_heat_rate_w(350.0, 300.0, 0.0) == pytest.approx(0.0)


def test_two_node_step_moves_temperatures_toward_each_other():
    from dac_sim.thermal import two_node_temperature_step

    next_1, next_2 = two_node_temperature_step(
        350.0, 2.0, 500.0,
        300.0, 1.0, 1000.0,
        10.0, 1.0,
    )
    assert 300.0 < next_2 < next_1 < 350.0


def test_two_node_step_conserves_sensible_energy():
    from dac_sim.thermal import (
        sensible_energy_change_j,
        two_node_temperature_step,
    )

    t1, t2 = 350.0, 300.0
    m1, cp1 = 2.0, 500.0
    m2, cp2 = 1.0, 1000.0

    next_1, next_2 = two_node_temperature_step(
        t1, m1, cp1, t2, m2, cp2, 10.0, 1.0
    )

    energy_1 = sensible_energy_change_j(m1, cp1, t1, next_1)
    energy_2 = sensible_energy_change_j(m2, cp2, t2, next_2)

    assert energy_1 + energy_2 == pytest.approx(0.0, abs=1e-9)


def test_negative_conductance_is_rejected():
    from dac_sim.thermal import thermal_link_heat_rate_w

    with pytest.raises(ValueError, match="cannot be negative"):
        thermal_link_heat_rate_w(350.0, 300.0, -1.0)


def test_two_node_step_rejects_non_finite_conductance():
    from dac_sim.thermal import two_node_temperature_step

    with pytest.raises(ValueError, match="finite number"):
        two_node_temperature_step(
            350.0, 2.0, 500.0,
            300.0, 1.0, 1000.0,
            float("nan"), 1.0,
        )


def test_network_conserves_energy():
    from dac_sim.thermal import (
        ThermalNode,
        ThermalLink,
        thermal_network_step,
        sensible_energy_change_j,
    )

    nodes = [
        ThermalNode("hot", 350.0, 2.0, 500.0),
        ThermalNode("cold", 300.0, 1.0, 1000.0),
    ]
    updated = thermal_network_step(
        nodes, [ThermalLink("hot", "cold", 10.0)], 1.0
    )

    energy_change = sum(
        sensible_energy_change_j(
            old.mass_kg,
            old.specific_heat_j_kg_k,
            old.temperature_k,
            new.temperature_k,
        )
        for old, new in zip(nodes, updated)
    )
    assert energy_change == pytest.approx(0.0, abs=1e-9)


def test_network_equal_temperatures_remain_unchanged():
    from dac_sim.thermal import ThermalNode, ThermalLink, thermal_network_step

    nodes = [
        ThermalNode("a", 320.0, 1.0, 500.0),
        ThermalNode("b", 320.0, 2.0, 1000.0),
    ]
    updated = thermal_network_step(
        nodes, [ThermalLink("a", "b", 10.0)], 1.0
    )
    assert [node.temperature_k for node in updated] == pytest.approx([320.0, 320.0])


def test_network_rejects_unknown_link_node():
    from dac_sim.thermal import ThermalNode, ThermalLink, thermal_network_step

    nodes = [ThermalNode("a", 320.0, 1.0, 500.0)]
    links = [ThermalLink("a", "missing", 10.0)]

    with pytest.raises(ValueError, match="unknown node"):
        thermal_network_step(nodes, links, 1.0)


def test_network_rejects_duplicate_node_names():
    from dac_sim.thermal import ThermalNode, thermal_network_step

    nodes = [
        ThermalNode("a", 320.0, 1.0, 500.0),
        ThermalNode("a", 300.0, 1.0, 500.0),
    ]

    with pytest.raises(ValueError, match="unique"):
        thermal_network_step(nodes, [], 1.0)


def test_network_rejects_invalid_time_step():
    from dac_sim.thermal import ThermalNode, thermal_network_step

    nodes = [ThermalNode("a", 320.0, 1.0, 500.0)]

    with pytest.raises(ValueError, match="greater than zero"):
        thermal_network_step(nodes, [], 0.0)


def test_network_external_heating_increases_temperature():
    from dac_sim.thermal import ThermalNode, thermal_network_step

    nodes = [ThermalNode("roller", 350.0, 2.0, 500.0)]
    updated = thermal_network_step(
        nodes, [], 10.0, external_heat_w={"roller": 500.0}
    )
    assert updated[0].temperature_k == pytest.approx(355.0)


def test_network_external_cooling_decreases_temperature():
    from dac_sim.thermal import ThermalNode, thermal_network_step

    nodes = [ThermalNode("roller", 350.0, 2.0, 500.0)]
    updated = thermal_network_step(
        nodes, [], 10.0, external_heat_w={"roller": -500.0}
    )
    assert updated[0].temperature_k == pytest.approx(345.0)


def test_network_rejects_external_heat_for_unknown_node():
    from dac_sim.thermal import ThermalNode, thermal_network_step

    nodes = [ThermalNode("roller", 350.0, 2.0, 500.0)]
    with pytest.raises(ValueError, match="unknown node"):
        thermal_network_step(
            nodes, [], 1.0, external_heat_w={"missing": 100.0}
        )


def test_oversized_network_step_is_rejected():
    from dac_sim.thermal import ThermalNode, ThermalLink, thermal_network_step

    nodes = [
        ThermalNode("hot", 350.0, 1.0, 100.0),
        ThermalNode("cold", 300.0, 1.0, 100.0),
    ]

    with pytest.raises(ValueError, match="too large"):
        thermal_network_step(
            nodes,
            [ThermalLink("hot", "cold", 10.0)],
            time_step_s=20.0,
        )



def test_network_rejects_oversized_three_node_step():
    from dac_sim.thermal import ThermalNode, ThermalLink, thermal_network_step

    nodes = [
        ThermalNode("center", 350.0, 1.0, 100.0),
        ThermalNode("left", 300.0, 1.0, 100.0),
        ThermalNode("right", 300.0, 1.0, 100.0),
    ]
    links = [
        ThermalLink("center", "left", 6.0),
        ThermalLink("center", "right", 6.0),
    ]

    with pytest.raises(ValueError, match="too large"):
        thermal_network_step(nodes, links, time_step_s=9.0)


def test_network_rejects_oversized_ambient_loss_step():
    from dac_sim.thermal import ThermalNode, thermal_network_step

    nodes = [ThermalNode("roller", 350.0, 1.0, 100.0)]

    with pytest.raises(ValueError, match="too large"):
        thermal_network_step(
            nodes,
            [],
            time_step_s=11.0,
            ambient_temperature_k=300.0,
            ambient_loss_conductance_w_k={"roller": 10.0},
        )
