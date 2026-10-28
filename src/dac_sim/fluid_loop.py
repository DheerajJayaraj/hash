"""Lumped thermal model for a roller wall coupled to a flowing fluid."""

from __future__ import annotations

import math
from dataclasses import dataclass


def _validate_finite(**values: float) -> None:
    for name, value in values.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{name} must be a finite number.")


@dataclass(frozen=True)
class FluidLoop:
    """A flowing fluid stream coupled to a thermal node.

    Attributes:
        node_name: The name of the thermal node where the fluid exchanges heat.
        mass_flow_rate_kg_s: Fluid mass flow rate [kg/s]. Must be non-negative.
        fluid_specific_heat_j_kg_k: Fluid isobaric specific heat capacity [J/(kg K)]. Must be positive.
        inlet_temperature_k: Inflow temperature of the fluid entering the node [K]. Must be positive.
    """

    node_name: str
    mass_flow_rate_kg_s: float
    fluid_specific_heat_j_kg_k: float
    inlet_temperature_k: float

    def __post_init__(self) -> None:
        if not isinstance(self.node_name, str) or not self.node_name.strip():
            raise ValueError("node_name must be a non-empty string.")
        _validate_finite(
            mass_flow_rate_kg_s=self.mass_flow_rate_kg_s,
            fluid_specific_heat_j_kg_k=self.fluid_specific_heat_j_kg_k,
            inlet_temperature_k=self.inlet_temperature_k,
        )
        if self.mass_flow_rate_kg_s < 0:
            raise ValueError("mass_flow_rate_kg_s cannot be negative.")
        if self.fluid_specific_heat_j_kg_k <= 0:
            raise ValueError("fluid_specific_heat_j_kg_k must be greater than zero.")
        if self.inlet_temperature_k <= 0:
            raise ValueError("inlet_temperature_k must be greater than zero K.")

    @property
    def flow_conductance_w_k(self) -> float:
        """Effective advective heat-capacity flow rate [W/K]."""
        return self.mass_flow_rate_kg_s * self.fluid_specific_heat_j_kg_k

    def heat_rate_to_node_w(self, node_temperature_k: float) -> float:
        """Heat transfer rate from the fluid stream into the node [W].

        Positive means the inflow warms the node (T_in > T_node).
        Negative means the flowing fluid cools the node (T_node > T_in),
        recovering heat from the node.
        """
        _validate_finite(node_temperature_k=node_temperature_k)
        if node_temperature_k <= 0:
            raise ValueError("node_temperature_k must be greater than zero K.")
        return self.flow_conductance_w_k * (
            self.inlet_temperature_k - node_temperature_k
        )



def fluid_wall_step(
    wall_temperature_k: float,
    wall_mass_kg: float,
    wall_specific_heat_j_kg_k: float,
    fluid_temperature_k: float,
    fluid_mass_kg: float,
    fluid_specific_heat_j_kg_k: float,
    fluid_inlet_temperature_k: float,
    mass_flow_rate_kg_s: float,
    wall_fluid_conductance_w_k: float,
    heater_power_w: float,
    ambient_temperature_k: float,
    wall_ambient_conductance_w_k: float,
    time_step_s: float,
) -> dict[str, float]:
    """Advance wall and well-mixed fluid temperatures by one Euler step.

    This lumped model does not resolve spatial temperature gradients,
    circulation delay, pressure drop, or pump energy.
    """
    _validate_finite(
        wall_temperature_k=wall_temperature_k,
        wall_mass_kg=wall_mass_kg,
        wall_specific_heat_j_kg_k=wall_specific_heat_j_kg_k,
        fluid_temperature_k=fluid_temperature_k,
        fluid_mass_kg=fluid_mass_kg,
        fluid_specific_heat_j_kg_k=fluid_specific_heat_j_kg_k,
        fluid_inlet_temperature_k=fluid_inlet_temperature_k,
        mass_flow_rate_kg_s=mass_flow_rate_kg_s,
        wall_fluid_conductance_w_k=wall_fluid_conductance_w_k,
        heater_power_w=heater_power_w,
        ambient_temperature_k=ambient_temperature_k,
        wall_ambient_conductance_w_k=wall_ambient_conductance_w_k,
        time_step_s=time_step_s,
    )

    if min(
        wall_temperature_k,
        fluid_temperature_k,
        fluid_inlet_temperature_k,
        ambient_temperature_k,
    ) <= 0:
        raise ValueError("All temperatures must be greater than zero K.")

    if min(
        wall_mass_kg,
        wall_specific_heat_j_kg_k,
        fluid_mass_kg,
        fluid_specific_heat_j_kg_k,
        time_step_s,
    ) <= 0:
        raise ValueError("Masses, heat capacities, and time step must be positive.")

    if min(
        mass_flow_rate_kg_s,
        wall_fluid_conductance_w_k,
        wall_ambient_conductance_w_k,
    ) < 0:
        raise ValueError("Flow rate and conductances cannot be negative.")

    wall_capacity_j_k = wall_mass_kg * wall_specific_heat_j_kg_k
    fluid_capacity_j_k = fluid_mass_kg * fluid_specific_heat_j_kg_k
    fluid_flow_conductance_w_k = (
        mass_flow_rate_kg_s * fluid_specific_heat_j_kg_k
    )

    # Coupled-system limit for non-oscillatory explicit Euler updates.
    a = (
        wall_fluid_conductance_w_k + wall_ambient_conductance_w_k
    ) / wall_capacity_j_k
    d = (
        wall_fluid_conductance_w_k + fluid_flow_conductance_w_k
    ) / fluid_capacity_j_k

    discriminant = (
        (a - d) ** 2
        + 4.0 * wall_fluid_conductance_w_k ** 2
        / (wall_capacity_j_k * fluid_capacity_j_k)
    )
    fastest_decay_rate_s = (
        a + d + math.sqrt(discriminant)
    ) / 2.0

    if fastest_decay_rate_s > 0 and time_step_s > (
        1.0 / fastest_decay_rate_s
    ):
        raise ValueError(
            "Time step is too large for stable coupled-system integration."
        )

    wall_fluid_heat_rate_w = wall_fluid_conductance_w_k * (
        fluid_temperature_k - wall_temperature_k
    )
    ambient_heat_rate_w = wall_ambient_conductance_w_k * (
        ambient_temperature_k - wall_temperature_k
    )
    fluid_flow_heat_rate_w = fluid_flow_conductance_w_k * (
        fluid_inlet_temperature_k - fluid_temperature_k
    )

    wall_net_heat_rate_w = (
        heater_power_w + wall_fluid_heat_rate_w + ambient_heat_rate_w
    )
    fluid_net_heat_rate_w = (
        -wall_fluid_heat_rate_w + fluid_flow_heat_rate_w
    )

    next_wall_temperature_k = wall_temperature_k + (
        wall_net_heat_rate_w * time_step_s / wall_capacity_j_k
    )
    next_fluid_temperature_k = fluid_temperature_k + (
        fluid_net_heat_rate_w * time_step_s / fluid_capacity_j_k
    )

    _validate_finite(
        next_wall_temperature_k=next_wall_temperature_k,
        next_fluid_temperature_k=next_fluid_temperature_k,
        wall_fluid_heat_rate_w=wall_fluid_heat_rate_w,
        ambient_heat_rate_w=ambient_heat_rate_w,
        fluid_flow_heat_rate_w=fluid_flow_heat_rate_w,
        wall_net_heat_rate_w=wall_net_heat_rate_w,
        fluid_net_heat_rate_w=fluid_net_heat_rate_w,
    )

    if min(next_wall_temperature_k, next_fluid_temperature_k) <= 0:
        raise ValueError(
            "Calculated temperature is at or below absolute zero; "
            "check the time step and parameters."
        )

    return {
        "wall_temperature_k": next_wall_temperature_k,
        "fluid_temperature_k": next_fluid_temperature_k,
        "wall_fluid_heat_rate_w": wall_fluid_heat_rate_w,
        "ambient_heat_rate_w": ambient_heat_rate_w,
        "fluid_flow_heat_rate_w": fluid_flow_heat_rate_w,
        "wall_net_heat_rate_w": wall_net_heat_rate_w,
        "fluid_net_heat_rate_w": fluid_net_heat_rate_w,
    }
