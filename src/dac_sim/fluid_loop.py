"""Lumped thermal model for a roller wall coupled to a flowing fluid."""

from __future__ import annotations

import math


def _validate_finite(**values: float) -> None:
    for name, value in values.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{name} must be a finite number.")


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
