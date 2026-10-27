"""Basic thermal calculations for the DAC simulation."""

from __future__ import annotations

import math


def _require_finite(name: str, value: float) -> None:
    """Require a finite numeric input, excluding booleans."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number.")


def _validate_node(
    temperature_k: float,
    mass_kg: float,
    specific_heat_j_kg_k: float,
) -> None:
    """Validate a lumped thermal node."""
    if temperature_k <= 0:
        raise ValueError("Temperature must be greater than zero K.")
    if mass_kg <= 0:
        raise ValueError("Mass must be greater than zero.")
    if specific_heat_j_kg_k <= 0:
        raise ValueError("Specific heat must be greater than zero.")


def temperature_step(
    temperature_k: float,
    mass_kg: float,
    specific_heat_j_kg_k: float,
    net_heat_rate_w: float,
    time_step_s: float,
) -> float:
    """Estimate a node's next temperature using an explicit energy balance.

    Positive net heat rate adds energy; negative net heat rate removes energy.
    Mass and specific heat are assumed constant during the time step.
    """
    inputs = {
        "temperature_k": temperature_k,
        "mass_kg": mass_kg,
        "specific_heat_j_kg_k": specific_heat_j_kg_k,
        "net_heat_rate_w": net_heat_rate_w,
        "time_step_s": time_step_s,
    }
    for name, value in inputs.items():
        _require_finite(name, value)

    _validate_node(temperature_k, mass_kg, specific_heat_j_kg_k)
    if time_step_s <= 0:
        raise ValueError("Time step must be greater than zero.")

    energy_change_j = net_heat_rate_w * time_step_s
    heat_capacity_j_k = mass_kg * specific_heat_j_kg_k
    next_temperature_k = temperature_k + energy_change_j / heat_capacity_j_k

    if not math.isfinite(next_temperature_k) or next_temperature_k <= 0:
        raise ValueError("Calculated temperature must be finite and above zero K.")

    return next_temperature_k


def sensible_energy_change_j(
    mass_kg: float,
    specific_heat_j_kg_k: float,
    initial_temperature_k: float,
    final_temperature_k: float,
) -> float:
    """Calculate sensible energy change [J] for constant mass and heat capacity."""
    inputs = {
        "mass_kg": mass_kg,
        "specific_heat_j_kg_k": specific_heat_j_kg_k,
        "initial_temperature_k": initial_temperature_k,
        "final_temperature_k": final_temperature_k,
    }
    for name, value in inputs.items():
        _require_finite(name, value)

    _validate_node(initial_temperature_k, mass_kg, specific_heat_j_kg_k)
    if final_temperature_k <= 0:
        raise ValueError("Final temperature must be greater than zero K.")

    return (
        mass_kg
        * specific_heat_j_kg_k
        * (final_temperature_k - initial_temperature_k)
    )


def thermal_link_heat_rate_w(
    temperature_1_k: float,
    temperature_2_k: float,
    conductance_w_k: float,
) -> float:
    """Return heat rate from node 1 to node 2 [W].

    Positive values mean heat flows from node 1 to node 2.
    The model assumes a constant thermal conductance.
    """
    _require_finite("temperature_1_k", temperature_1_k)
    _require_finite("temperature_2_k", temperature_2_k)
    _require_finite("conductance_w_k", conductance_w_k)

    if temperature_1_k <= 0 or temperature_2_k <= 0:
        raise ValueError("Temperatures must be greater than zero K.")
    if conductance_w_k < 0:
        raise ValueError("Thermal conductance cannot be negative.")

    return conductance_w_k * (temperature_1_k - temperature_2_k)


def two_node_temperature_step(
    temperature_1_k: float,
    mass_1_kg: float,
    specific_heat_1_j_kg_k: float,
    temperature_2_k: float,
    mass_2_kg: float,
    specific_heat_2_j_kg_k: float,
    conductance_w_k: float,
    time_step_s: float,
) -> tuple[float, float]:
    """Advance two nodes coupled by one thermal link using explicit Euler.

    Returns:
        A tuple (next_temperature_1_k, next_temperature_2_k).

    Notes:
        The same heat rate is removed from node 1 and added to node 2.
        This conserves total sensible energy for constant heat capacities.
        Explicit Euler can overshoot equilibrium if the time step is too large;
        choose a time step suitable for the system's thermal time constants.
    """
    values = {
        "temperature_1_k": temperature_1_k,
        "mass_1_kg": mass_1_kg,
        "specific_heat_1_j_kg_k": specific_heat_1_j_kg_k,
        "temperature_2_k": temperature_2_k,
        "mass_2_kg": mass_2_kg,
        "specific_heat_2_j_kg_k": specific_heat_2_j_kg_k,
        "conductance_w_k": conductance_w_k,
        "time_step_s": time_step_s,
    }
    for name, value in values.items():
        _require_finite(name, value)

    _validate_node(temperature_1_k, mass_1_kg, specific_heat_1_j_kg_k)
    _validate_node(temperature_2_k, mass_2_kg, specific_heat_2_j_kg_k)

    if conductance_w_k < 0:
        raise ValueError("Thermal conductance cannot be negative.")
    if time_step_s <= 0:
        raise ValueError("Time step must be greater than zero.")

    heat_rate_w = thermal_link_heat_rate_w(
        temperature_1_k, temperature_2_k, conductance_w_k
    )
    energy_transferred_j = heat_rate_w * time_step_s

    next_temperature_1_k = temperature_1_k - energy_transferred_j / (
        mass_1_kg * specific_heat_1_j_kg_k
    )
    next_temperature_2_k = temperature_2_k + energy_transferred_j / (
        mass_2_kg * specific_heat_2_j_kg_k
    )

    if (
        not math.isfinite(next_temperature_1_k)
        or not math.isfinite(next_temperature_2_k)
        or next_temperature_1_k <= 0
        or next_temperature_2_k <= 0
    ):
        raise ValueError(
            "Calculated temperatures must be finite and above zero K. "
            "Check the time step and thermal parameters."
        )

    return next_temperature_1_k, next_temperature_2_k
from dataclasses import dataclass


@dataclass(frozen=True)
class ThermalNode:
    """A lumped thermal node with constant mass and specific heat capacity."""

    name: str
    temperature_k: float
    mass_kg: float
    specific_heat_j_kg_k: float

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Node name must be a non-empty string.")

        for field_name in (
            "temperature_k",
            "mass_kg",
            "specific_heat_j_kg_k",
        ):
            value = getattr(self, field_name)
            _require_finite(field_name, value)

        _validate_node(
            self.temperature_k,
            self.mass_kg,
            self.specific_heat_j_kg_k,
        )


@dataclass(frozen=True)
class ThermalLink:
    """A conductive link between two named thermal nodes."""

    node_1: str
    node_2: str
    conductance_w_k: float

    def __post_init__(self) -> None:
        if not isinstance(self.node_1, str) or not self.node_1.strip():
            raise ValueError("node_1 must be a non-empty string.")
        if not isinstance(self.node_2, str) or not self.node_2.strip():
            raise ValueError("node_2 must be a non-empty string.")
        if self.node_1 == self.node_2:
            raise ValueError("A thermal link must connect two different nodes.")

        _require_finite("conductance_w_k", self.conductance_w_k)
        if self.conductance_w_k < 0:
            raise ValueError("Thermal conductance cannot be negative.")


def thermal_network_step(
    nodes: list[ThermalNode],
    links: list[ThermalLink],
    time_step_s: float,
    external_heat_w: dict[str, float] | None = None,
    ambient_temperature_k: float = 298.15,
    ambient_loss_conductance_w_k: dict[str, float] | None = None,
) -> list[ThermalNode]:
    """Advance a thermal network by one explicit Euler time step.

    external_heat_w maps node names to external heat rates in watts.
    Positive values add heat; negative values remove heat.

    ambient_loss_conductance_w_k maps node names to non-negative heat-loss
    conductances in W/K. Heat exchange with ambient is calculated as
    -G_loss * (T_node - T_ambient). A node colder than ambient gains heat.

    Nodes not listed in either mapping have zero external heat input and
    zero ambient heat-loss conductance.
    """
    _require_finite("time_step_s", time_step_s)
    _require_finite("ambient_temperature_k", ambient_temperature_k)

    if time_step_s <= 0:
        raise ValueError("Time step must be greater than zero.")
    if ambient_temperature_k <= 0:
        raise ValueError("Ambient temperature must be greater than zero K.")
    if not nodes:
        raise ValueError("At least one thermal node is required.")

    node_by_name = {node.name: node for node in nodes}
    if len(node_by_name) != len(nodes):
        raise ValueError("Thermal node names must be unique.")

    external_heat_w = {} if external_heat_w is None else external_heat_w
    ambient_loss_conductance_w_k = (
        {}
        if ambient_loss_conductance_w_k is None
        else ambient_loss_conductance_w_k
    )

    for name, rate in external_heat_w.items():
        if name not in node_by_name:
            raise ValueError(f"External heat references unknown node: {name!r}.")
        _require_finite(f"external_heat_w[{name!r}]", rate)

    for name, conductance in ambient_loss_conductance_w_k.items():
        if name not in node_by_name:
            raise ValueError(
                f"Ambient heat loss references unknown node: {name!r}."
            )
        _require_finite(
            f"ambient_loss_conductance_w_k[{name!r}]", conductance
        )
        if conductance < 0:
            raise ValueError("Ambient heat-loss conductance cannot be negative.")

    net_heat_w = {node.name: 0.0 for node in nodes}

    for link in links:
        if link.node_1 not in node_by_name or link.node_2 not in node_by_name:
            raise ValueError(
                f"Thermal link references an unknown node: "
                f"{link.node_1!r}, {link.node_2!r}."
            )

        node_1 = node_by_name[link.node_1]
        node_2 = node_by_name[link.node_2]
        heat_rate_w = thermal_link_heat_rate_w(
            node_1.temperature_k,
            node_2.temperature_k,
            link.conductance_w_k,
        )

        net_heat_w[link.node_1] -= heat_rate_w
        net_heat_w[link.node_2] += heat_rate_w

    for name, rate in external_heat_w.items():
        net_heat_w[name] += rate

    for node in nodes:
        conductance = ambient_loss_conductance_w_k.get(node.name, 0.0)
        ambient_heat_rate_w = conductance * (
            ambient_temperature_k - node.temperature_k
        )
        net_heat_w[node.name] += ambient_heat_rate_w

    # Enforce a conservative explicit-Euler step limit that prevents
    # conductive coupling alone from reversing the temperature ordering.
    total_conductance_w_k = {node.name: 0.0 for node in nodes}

    for link in links:
        total_conductance_w_k[link.node_1] += link.conductance_w_k
        total_conductance_w_k[link.node_2] += link.conductance_w_k

    for node in nodes:
        total_conductance_w_k[node.name] += (
            ambient_loss_conductance_w_k.get(node.name, 0.0)
        )

    fastest_node_rate_per_s = max(
        total_conductance_w_k[node.name]
        / (node.mass_kg * node.specific_heat_j_kg_k)
        for node in nodes
    )

    if (
        fastest_node_rate_per_s > 0.0
        and time_step_s > 1.0 / fastest_node_rate_per_s
    ):
        raise ValueError(
            "Time step is too large for monotonic explicit-Euler "
            "thermal integration. Reduce time_step_s."
        )
    updated_nodes = []
    for node in nodes:
        next_temperature = temperature_step(
            temperature_k=node.temperature_k,
            mass_kg=node.mass_kg,
            specific_heat_j_kg_k=node.specific_heat_j_kg_k,
            net_heat_rate_w=net_heat_w[node.name],
            time_step_s=time_step_s,
        )
        updated_nodes.append(
            ThermalNode(
                name=node.name,
                temperature_k=next_temperature,
                mass_kg=node.mass_kg,
                specific_heat_j_kg_k=node.specific_heat_j_kg_k,
            )
        )

    return updated_nodes
