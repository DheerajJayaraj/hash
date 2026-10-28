import pytest
import yaml
from pathlib import Path

from dac_sim.prototype import build_prototype_network


@pytest.fixture
def assumptions():
    with Path("assumptions.yaml").open(encoding="utf-8-sig") as file:
        return yaml.safe_load(file)


@pytest.fixture
def properties():
    return {
        "hot_roller": (2.0, 500.0),
        "belt_sorbent": (0.5, 1000.0),
        "intermediate_loop": (1.0, 4180.0),
        "cooling_roller": (2.0, 500.0),
    }


@pytest.fixture
def conductances():
    return {
        "hot_roller_to_belt": 10.0,
        "belt_to_intermediate_loop": 5.0,
        "belt_to_cooling_roller": 8.0,
    }


def test_builder_uses_assumption_temperatures(
    assumptions, properties, conductances
):
    nodes, _, _ = build_prototype_network(
        assumptions, properties, conductances, 320.0
    )
    temperatures = {node.name: node.temperature_k for node in nodes}

    assert temperatures["hot_roller"] == pytest.approx(378.15)
    assert temperatures["belt_sorbent"] == pytest.approx(320.0)
    assert temperatures["intermediate_loop"] == pytest.approx(338.15)
    assert temperatures["cooling_roller"] == pytest.approx(298.15)


def test_builder_uses_configured_heater_power(
    assumptions, properties, conductances
):
    _, _, heater = build_prototype_network(
        assumptions, properties, conductances, 320.0
    )
    assert heater == {"hot_roller": 500.0}


def test_builder_creates_expected_links(
    assumptions, properties, conductances
):
    _, links, _ = build_prototype_network(
        assumptions, properties, conductances, 320.0
    )
    connections = {(link.node_1, link.node_2) for link in links}

    assert connections == {
        ("hot_roller", "belt_sorbent"),
        ("belt_sorbent", "intermediate_loop"),
        ("belt_sorbent", "cooling_roller"),
    }


def test_builder_rejects_missing_thermal_properties(
    assumptions, conductances
):
    with pytest.raises(ValueError, match="Missing thermal properties"):
        build_prototype_network(
            assumptions, {}, conductances, 320.0
        )


def test_builder_rejects_missing_conductance(
    assumptions, properties
):
    with pytest.raises(ValueError, match="Missing conductances"):
        build_prototype_network(
            assumptions, properties, {}, 320.0
        )


def test_builder_rejects_non_numeric_belt_temperature(
    assumptions, properties, conductances
):
    with pytest.raises(ValueError, match="Belt temperature must be numeric"):
        build_prototype_network(
            assumptions, properties, conductances, "320"
        )


def test_builder_rejects_zero_belt_temperature(
    assumptions, properties, conductances
):
    with pytest.raises(ValueError, match="greater than zero K"):
        build_prototype_network(
            assumptions, properties, conductances, 0.0
        )
