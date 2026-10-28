"""Prototype thermal network assembly for the roller-belt DAC system."""

from __future__ import annotations

from typing import Any

from dac_sim.fluid_loop import FluidLoop
from dac_sim.thermal import ThermalLink, ThermalNode


NODE_NAMES = (
    "hot_roller",
    "belt_sorbent",
    "intermediate_loop",
    "cooling_roller",
)

LINK_NAMES = (
    "hot_roller_to_belt",
    "belt_to_intermediate_loop",
    "belt_to_cooling_roller",
)


def build_prototype_network(
    assumptions: dict[str, Any],
    thermal_properties: dict[str, tuple[float, float]],
    conductances_w_k: dict[str, float],
    belt_temperature_k: float,
) -> tuple[list[ThermalNode], list[ThermalLink], dict[str, float]]:
    """Build a four-node prototype network.

    thermal_properties maps each node name to (mass_kg, specific_heat_J_kg_K).
    conductances_w_k maps each LINK_NAMES entry to a conductance in W/K.

    Returns:
        (nodes, links, external_heat_w)

    The heater input is applied to the hot-roller node. This assumes the
    configured heater power is fully delivered to that node; it does not
    account for heater efficiency, losses, or temperature control.
    """
    project = assumptions.get("project", {})
    prototype_entry = project.get("prototype", {})
    prototype = prototype_entry.get("value", {})

    required_temperature_keys = {
        "hot_roller": "hot_roller_temperature",
        "intermediate_loop": "intermediate_loop_temperature",
        "cooling_roller": "cooling_roller_temperature",
    }

    temperatures = {}
    for node_name, assumption_key in required_temperature_keys.items():
        entry = project.get(assumption_key)
        if not isinstance(entry, dict) or "value" not in entry:
            raise ValueError(
                f"Missing temperature assumption: {assumption_key}"
            )
        temperatures[node_name] = entry["value"]

    temperatures["belt_sorbent"] = belt_temperature_k

    if not isinstance(belt_temperature_k, (int, float)) or isinstance(
        belt_temperature_k, bool
    ):
        raise ValueError("Belt temperature must be numeric.")

    missing_properties = set(NODE_NAMES) - set(thermal_properties)
    if missing_properties:
        raise ValueError(
            f"Missing thermal properties for: {sorted(missing_properties)}"
        )

    missing_links = set(LINK_NAMES) - set(conductances_w_k)
    if missing_links:
        raise ValueError(
            f"Missing conductances for: {sorted(missing_links)}"
        )

    nodes = []
    for name in NODE_NAMES:
        properties = thermal_properties[name]
        if not isinstance(properties, (tuple, list)) or len(properties) != 2:
            raise ValueError(
                f"{name} properties must be (mass_kg, specific_heat_J_kg_K)."
            )

        mass_kg, specific_heat_j_kg_k = properties
        nodes.append(
            ThermalNode(
                name=name,
                temperature_k=temperatures[name],
                mass_kg=mass_kg,
                specific_heat_j_kg_k=specific_heat_j_kg_k,
            )
        )

    links = [
        ThermalLink(
            "hot_roller",
            "belt_sorbent",
            conductances_w_k["hot_roller_to_belt"],
        ),
        ThermalLink(
            "belt_sorbent",
            "intermediate_loop",
            conductances_w_k["belt_to_intermediate_loop"],
        ),
        ThermalLink(
            "belt_sorbent",
            "cooling_roller",
            conductances_w_k["belt_to_cooling_roller"],
        ),
    ]

    heater_power_w = prototype.get("heater_power")
    if heater_power_w is None:
        raise ValueError("Missing prototype heater_power assumption.")

    return nodes, links, {"hot_roller": heater_power_w}


def build_prototype_fluid_loop(
    assumptions: dict[str, Any],
    node_name: str = "intermediate_loop",
    flow_rate_l_min: float | None = None,
    fluid_density_kg_m3: float = 1000.0,
    fluid_specific_heat_j_kg_k: float = 4180.0,
    inlet_temperature_k: float | None = None,
) -> FluidLoop:
    """Build a FluidLoop instance configured from prototype assumptions.

    flow_rate_l_min defaults to loop_flow_min from prototype assumptions.
    inlet_temperature_k defaults to intermediate_loop_temperature.
    """
    project = assumptions.get("project", {})
    prototype_entry = project.get("prototype", {})
    prototype = prototype_entry.get("value", {})

    if flow_rate_l_min is None:
        flow_rate_l_min = prototype.get("loop_flow_min", 0.5)

    if not isinstance(flow_rate_l_min, (int, float)) or isinstance(
        flow_rate_l_min, bool
    ):
        raise ValueError("flow_rate_l_min must be numeric.")
    if flow_rate_l_min < 0:
        raise ValueError("flow_rate_l_min cannot be negative.")

    if inlet_temperature_k is None:
        temp_entry = project.get("intermediate_loop_temperature")
        if isinstance(temp_entry, dict) and "value" in temp_entry:
            inlet_temperature_k = temp_entry["value"]
        else:
            inlet_temperature_k = 338.15

    # Convert L/min to kg/s: (L/min) * (0.001 m3/L) * (rho kg/m3) / 60 s
    mass_flow_rate_kg_s = (flow_rate_l_min * 0.001 * fluid_density_kg_m3) / 60.0

    return FluidLoop(
        node_name=node_name,
        mass_flow_rate_kg_s=mass_flow_rate_kg_s,
        fluid_specific_heat_j_kg_k=fluid_specific_heat_j_kg_k,
        inlet_temperature_k=inlet_temperature_k,
    )
