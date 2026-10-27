"""Transient simulation runner for the DAC thermal network."""

from __future__ import annotations

import math

from dac_sim.thermal import (
    ThermalLink,
    ThermalNode,
    sensible_energy_change_j,
    thermal_network_step,
)


def run_thermal_simulation(
    nodes: list[ThermalNode],
    links: list[ThermalLink],
    duration_s: float,
    time_step_s: float,
    external_heat_w: dict[str, float] | None = None,
    ambient_temperature_k: float = 298.15,
    ambient_loss_conductance_w_k: dict[str, float] | None = None,
) -> dict[str, object]:
    """Simulate a thermal network and record its temperature history.

    External heat rates and ambient temperature are held constant.
    Ambient heat exchange is calculated using the node temperatures at the
    start of each step, consistent with explicit Euler integration.

    Returns time and temperature histories, cumulative external energy,
    cumulative ambient energy exchange, internal energy change, and balance
    error. Positive ambient energy means the surroundings heated the nodes;
    negative ambient energy means the nodes lost heat to the surroundings.
    """
    for name, value in (
        ("duration_s", duration_s),
        ("time_step_s", time_step_s),
        ("ambient_temperature_k", ambient_temperature_k),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{name} must be a finite number.")

    if duration_s <= 0:
        raise ValueError("Duration must be greater than zero.")
    if time_step_s <= 0:
        raise ValueError("Time step must be greater than zero.")
    if ambient_temperature_k <= 0:
        raise ValueError("Ambient temperature must be greater than zero K.")
    if not nodes:
        raise ValueError("At least one thermal node is required.")

    initial_nodes = list(nodes)
    current_nodes = list(nodes)
    node_names = [node.name for node in current_nodes]

    if len(set(node_names)) != len(node_names):
        raise ValueError("Thermal node names must be unique.")

    external_heat_w = (
        {} if external_heat_w is None else dict(external_heat_w)
    )
    ambient_loss_conductance_w_k = (
        {}
        if ambient_loss_conductance_w_k is None
        else dict(ambient_loss_conductance_w_k)
    )

    for name, rate in external_heat_w.items():
        if name not in node_names:
            raise ValueError(f"External heat references unknown node: {name!r}.")
        if (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
        ):
            raise ValueError(f"External heat for {name!r} must be finite.")

    for name, conductance in ambient_loss_conductance_w_k.items():
        if name not in node_names:
            raise ValueError(
                f"Ambient heat loss references unknown node: {name!r}."
            )
        if (
            isinstance(conductance, bool)
            or not isinstance(conductance, (int, float))
            or not math.isfinite(conductance)
        ):
            raise ValueError(
                f"Ambient heat-loss conductance for {name!r} must be finite."
            )
        if conductance < 0:
            raise ValueError(
                "Ambient heat-loss conductance cannot be negative."
            )

    time_s = [0.0]
    temperature_history_k = {
        node.name: [node.temperature_k] for node in current_nodes
    }
    external_energy_j = 0.0
    ambient_energy_j = 0.0
    elapsed_s = 0.0

    while elapsed_s < duration_s:
        dt = min(time_step_s, duration_s - elapsed_s)

        # Explicit Euler: calculate ambient exchange from start-of-step
        # temperatures, matching the temperature update in thermal.py.
        ambient_rate_w = sum(
            conductance
            * (ambient_temperature_k - node.temperature_k)
            for node in current_nodes
            for conductance in [
                ambient_loss_conductance_w_k.get(node.name, 0.0)
            ]
        )

        current_nodes = thermal_network_step(
            current_nodes,
            links,
            dt,
            external_heat_w=external_heat_w,
            ambient_temperature_k=ambient_temperature_k,
            ambient_loss_conductance_w_k=ambient_loss_conductance_w_k,
        )

        external_energy_j += sum(external_heat_w.values()) * dt
        ambient_energy_j += ambient_rate_w * dt
        elapsed_s += dt

        if math.isclose(
            elapsed_s, duration_s, rel_tol=1e-12, abs_tol=1e-12
        ):
            elapsed_s = duration_s

        time_s.append(elapsed_s)
        for node in current_nodes:
            temperature_history_k[node.name].append(node.temperature_k)

    internal_energy_change_j = sum(
        sensible_energy_change_j(
            initial.mass_kg,
            initial.specific_heat_j_kg_k,
            initial.temperature_k,
            final.temperature_k,
        )
        for initial, final in zip(initial_nodes, current_nodes)
    )

    total_energy_input_j = external_energy_j + ambient_energy_j

    return {
        "time_s": time_s,
        "temperature_history_k": temperature_history_k,
        "external_energy_j": external_energy_j,
        "ambient_energy_j": ambient_energy_j,
        "total_internal_energy_change_j": internal_energy_change_j,
        "energy_balance_error_j": internal_energy_change_j - total_energy_input_j,
    }
