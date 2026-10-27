"""Compare illustrative roller constructions using thermal mass and energy.

All material properties and the fluid fill fraction are ASSUMED placeholders.
This module does not yet simulate fluid circulation or contact heat transfer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RollerCase:
    """Thermal properties of one illustrative roller configuration."""

    name: str
    metal_mass_kg: float
    fluid_mass_kg: float
    metal_heat_capacity_j_kg_k: float
    fluid_heat_capacity_j_kg_k: float

    @property
    def total_heat_capacity_j_k(self) -> float:
        return (
            self.metal_mass_kg * self.metal_heat_capacity_j_kg_k
            + self.fluid_mass_kg * self.fluid_heat_capacity_j_kg_k
        )


def compare_roller_options(
    outer_diameter_m: float,
    face_width_m: float,
    wall_thickness_m: float,
    initial_temperature_k: float,
    target_temperature_k: float,
    heater_power_w: float,
    fluid_fill_fraction: float = 0.7,
    metal_density_kg_m3: float = 2700.0,
    metal_specific_heat_j_kg_k: float = 900.0,
    fluid_density_kg_m3: float = 1030.0,
    fluid_specific_heat_j_kg_k: float = 3800.0,
) -> list[dict[str, float | str]]:
    """Compare ideal sensible heating for solid, hollow, and fluid-filled rollers.

    Assumptions:
    - Cylindrical geometry with a uniform face width.
    - The hollow roller has a uniform metal shell.
    - The fluid-filled case treats the fluid as a static thermal mass.
    - No ambient losses, contact resistance, circulation losses, or phase changes.
    - Ideal heating time equals sensible energy divided by heater power.
    """
    values = {
        "outer_diameter_m": outer_diameter_m,
        "face_width_m": face_width_m,
        "wall_thickness_m": wall_thickness_m,
        "initial_temperature_k": initial_temperature_k,
        "target_temperature_k": target_temperature_k,
        "heater_power_w": heater_power_w,
        "fluid_fill_fraction": fluid_fill_fraction,
        "metal_density_kg_m3": metal_density_kg_m3,
        "metal_specific_heat_j_kg_k": metal_specific_heat_j_kg_k,
        "fluid_density_kg_m3": fluid_density_kg_m3,
        "fluid_specific_heat_j_kg_k": fluid_specific_heat_j_kg_k,
    }

    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be numeric.")
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite.")

    for name in (
        "outer_diameter_m",
        "face_width_m",
        "wall_thickness_m",
        "heater_power_w",
        "metal_density_kg_m3",
        "metal_specific_heat_j_kg_k",
        "fluid_density_kg_m3",
        "fluid_specific_heat_j_kg_k",
    ):
        if values[name] <= 0:
            raise ValueError(f"{name} must be greater than zero.")

    if not 0 < wall_thickness_m < outer_diameter_m / 2:
        raise ValueError("Wall thickness must be less than the outer radius.")

    if not 0 <= fluid_fill_fraction <= 1:
        raise ValueError("Fluid fill fraction must be between 0 and 1.")

    if initial_temperature_k <= 0 or target_temperature_k <= 0:
        raise ValueError("Temperatures must be above zero K.")

    if target_temperature_k < initial_temperature_k:
        raise ValueError("Target temperature must not be below initial temperature.")

    outer_radius_m = outer_diameter_m / 2
    inner_radius_m = outer_radius_m - wall_thickness_m
    length_m = face_width_m

    solid_volume_m3 = math.pi * outer_radius_m**2 * length_m
    shell_volume_m3 = (
        math.pi * (outer_radius_m**2 - inner_radius_m**2) * length_m
    )
    internal_volume_m3 = math.pi * inner_radius_m**2 * length_m

    solid_mass_kg = solid_volume_m3 * metal_density_kg_m3
    shell_mass_kg = shell_volume_m3 * metal_density_kg_m3
    fluid_mass_kg = (
        internal_volume_m3 * fluid_fill_fraction * fluid_density_kg_m3
    )

    cases = [
        RollerCase(
            "solid",
            solid_mass_kg,
            0.0,
            metal_specific_heat_j_kg_k,
            fluid_specific_heat_j_kg_k,
        ),
        RollerCase(
            "hollow",
            shell_mass_kg,
            0.0,
            metal_specific_heat_j_kg_k,
            fluid_specific_heat_j_kg_k,
        ),
        RollerCase(
            "hollow_with_static_fluid",
            shell_mass_kg,
            fluid_mass_kg,
            metal_specific_heat_j_kg_k,
            fluid_specific_heat_j_kg_k,
        ),
    ]

    temperature_change_k = target_temperature_k - initial_temperature_k
    results = []

    for case in cases:
        energy_j = case.total_heat_capacity_j_k * temperature_change_k
        results.append(
            {
                "configuration": case.name,
                "metal_mass_kg": case.metal_mass_kg,
                "fluid_mass_kg": case.fluid_mass_kg,
                "heat_capacity_j_k": case.total_heat_capacity_j_k,
                "ideal_heating_energy_j": energy_j,
                "ideal_heating_time_s": energy_j / heater_power_w,
            }
        )

    return results
