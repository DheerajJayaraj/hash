"""Sorbent equilibrium and kinetic calculations for DAC adsorption and desorption."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# CO2 molecular weight: 44.0095 g/mol = 0.0440095 kg/mol
CO2_MOLAR_MASS_KG_MOL = 0.0440095
CO2_MOLAR_MASS_G_MOL = 44.0095


def _require_finite(name: str, value: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number.")


@dataclass(frozen=True)
class SorbentProperties:
    """Physically grounded properties for a solid DAC sorbent.

    Attributes:
        working_capacity_mol_kg: Maximum equilibrium working capacity at
            ambient adsorption conditions [mol CO2 / kg sorbent].
            Default 1.0 mol/kg (1.0 mmol/g).
        uptake_rate_mol_kg_s: Initial uptake rate [mol CO2 / (kg sorbent s)]
            at ambient air conditions. Default 0.065 mmol/g/min = 1.0833e-3 mol/(kg s).
        desorption_heat_j_kg: Heat of desorption per unit mass of CO2 desorbed
            [J / kg CO2]. Default 1.6 MWh/t_CO2 = 5.76e6 J/kg CO2 (130.9 kJ/mol CO2).
        desorption_rate_s: First-order desorption rate constant at nominal
            regeneration temperature [1/s]. Default 0.015 1/s (tau ~ 67 s).
        desorption_temp_onset_k: Temperature where desorption begins [K].
            Default 338.15 K (65 C).
        desorption_temp_peak_k: Temperature where desorption reaches nominal
            regeneration rate [K]. Default 378.15 K (105 C).
        residual_capacity_fraction: Fraction of capacity remaining at peak
            regeneration temperature (un-desorbed baseline). Default 0.05.
    """

    working_capacity_mol_kg: float = 1.0
    uptake_rate_mol_kg_s: float = 0.065 / 60.0
    desorption_heat_j_kg: float = 1.6 * 3.6e6
    desorption_rate_s: float = 0.015
    desorption_temp_onset_k: float = 338.15
    desorption_temp_peak_k: float = 378.15
    residual_capacity_fraction: float = 0.05

    def __post_init__(self) -> None:
        for field in (
            "working_capacity_mol_kg",
            "uptake_rate_mol_kg_s",
            "desorption_heat_j_kg",
            "desorption_rate_s",
            "desorption_temp_onset_k",
            "desorption_temp_peak_k",
            "residual_capacity_fraction",
        ):
            val = getattr(self, field)
            _require_finite(field, val)

        if self.working_capacity_mol_kg <= 0:
            raise ValueError("working_capacity_mol_kg must be positive.")
        if self.uptake_rate_mol_kg_s <= 0:
            raise ValueError("uptake_rate_mol_kg_s must be positive.")
        if self.desorption_heat_j_kg <= 0:
            raise ValueError("desorption_heat_j_kg must be positive.")
        if self.desorption_rate_s <= 0:
            raise ValueError("desorption_rate_s must be positive.")
        if self.desorption_temp_onset_k <= 0:
            raise ValueError("desorption_temp_onset_k must be positive.")
        if self.desorption_temp_peak_k <= self.desorption_temp_onset_k:
            raise ValueError(
                "desorption_temp_peak_k must be greater than desorption_temp_onset_k."
            )
        if not (0.0 <= self.residual_capacity_fraction < 1.0):
            raise ValueError(
                "residual_capacity_fraction must be in range [0, 1)."
            )

    @property
    def max_loading_kg_co2_kg_sorbent(self) -> float:
        """Maximum gravimetric loading [kg CO2 / kg sorbent]."""
        return self.working_capacity_mol_kg * CO2_MOLAR_MASS_KG_MOL

    @classmethod
    def from_assumptions(cls, assumptions: dict[str, Any]) -> SorbentProperties:
        """Create SorbentProperties from the assumptions register."""
        project = assumptions.get("project", {})

        def _val(key: str, default: float) -> float:
            entry = project.get(key)
            if isinstance(entry, dict) and "value" in entry:
                return float(entry["value"])
            return default

        working_cap_mmol_g = _val("working_capacity", 1.0)
        # 1 mmol/g = 1 mol/kg
        working_cap_mol_kg = working_cap_mmol_g

        uptake_mmol_g_min = _val("uptake_rate", 0.065)
        # mmol/(g min) -> mol/(kg s) = (mmol/g * 1) / 60
        uptake_rate_mol_kg_s = uptake_mmol_g_min / 60.0

        desorption_heat_mwh_t = _val("desorption_heat", 1.6)
        # MWh/t -> J/kg: 1 MWh/t = 3.6e9 J / 1000 kg = 3.6e6 J/kg
        desorption_heat_j_kg = desorption_heat_mwh_t * 3.6e6

        hot_roller_k = _val("hot_roller_temperature", 378.15)
        intermediate_k = _val("intermediate_loop_temperature", 338.15)

        return cls(
            working_capacity_mol_kg=working_cap_mol_kg,
            uptake_rate_mol_kg_s=uptake_rate_mol_kg_s,
            desorption_heat_j_kg=desorption_heat_j_kg,
            desorption_rate_s=0.015,
            desorption_temp_onset_k=intermediate_k,
            desorption_temp_peak_k=hot_roller_k,
            residual_capacity_fraction=0.05,
        )


def equilibrium_capacity_mol_kg(
    temperature_k: float,
    properties: SorbentProperties,
) -> float:
    """Calculate temperature-dependent equilibrium CO2 loading [mol CO2 / kg sorbent].

    Amine solid sorbents exhibit a sharp loss in equilibrium capacity as
    temperature rises above ~60-70 C. A smooth logistic thermal-swing function
    is used between ambient adsorption and hot desorption temperatures.
    """
    _require_finite("temperature_k", temperature_k)
    if temperature_k <= 0:
        raise ValueError("temperature_k must be positive.")

    t_onset = properties.desorption_temp_onset_k
    t_peak = properties.desorption_temp_peak_k
    t_mid = (t_onset + t_peak) / 2.0
    width = max(1.0, (t_peak - t_onset) / 4.0)

    # Normalized temperature logistic swing: 1 at low T, 0 at high T
    logistic = 1.0 / (1.0 + math.exp(min(50.0, max(-50.0, (temperature_k - t_mid) / width))))

    q_residual = (
        properties.working_capacity_mol_kg * properties.residual_capacity_fraction
    )
    q_swing = properties.working_capacity_mol_kg * (
        1.0 - properties.residual_capacity_fraction
    )

    return q_residual + q_swing * logistic


def adsorption_rate_mol_kg_s(
    current_loading_mol_kg: float,
    temperature_k: float,
    properties: SorbentProperties,
) -> float:
    """Calculate adsorption rate dq/dt [mol CO2 / (kg sorbent s)].

    Uses linear driving force kinetics: dq/dt = k_ads * (q_eq(T) - q)
    when current_loading < q_eq(T), where k_ads = uptake_rate / q_max.
    Returns 0 when current_loading >= q_eq(T).
    """
    _require_finite("current_loading_mol_kg", current_loading_mol_kg)
    _require_finite("temperature_k", temperature_k)

    if current_loading_mol_kg < 0:
        raise ValueError("current_loading_mol_kg cannot be negative.")
    if temperature_k <= 0:
        raise ValueError("temperature_k must be positive.")

    q_eq = equilibrium_capacity_mol_kg(temperature_k, properties)
    if current_loading_mol_kg >= q_eq:
        return 0.0

    # Rate constant k_ads [1/s]
    k_ads = properties.uptake_rate_mol_kg_s / properties.working_capacity_mol_kg
    driving_force = q_eq - current_loading_mol_kg
    return k_ads * driving_force


def desorption_rate_mol_kg_s(
    current_loading_mol_kg: float,
    temperature_k: float,
    properties: SorbentProperties,
) -> float:
    """Calculate desorption rate -dq/dt [mol CO2 / (kg sorbent s)].

    Positive value represents the rate of CO2 release.
    Desorption is thermally activated when temperature exceeds onset temperature.
    Uses: -dq/dt = k_des(T) * (q - q_eq(T)) when q > q_eq(T).
    """
    _require_finite("current_loading_mol_kg", current_loading_mol_kg)
    _require_finite("temperature_k", temperature_k)

    if current_loading_mol_kg < 0:
        raise ValueError("current_loading_mol_kg cannot be negative.")
    if temperature_k <= 0:
        raise ValueError("temperature_k must be positive.")

    q_eq = equilibrium_capacity_mol_kg(temperature_k, properties)
    if current_loading_mol_kg <= q_eq:
        return 0.0

    # Temperature activation factor: smoothly activates between onset and peak
    t_onset = properties.desorption_temp_onset_k
    t_peak = properties.desorption_temp_peak_k

    if temperature_k <= t_onset:
        return 0.0

    temp_factor = min(1.0, (temperature_k - t_onset) / (t_peak - t_onset))
    k_des = properties.desorption_rate_s * (temp_factor ** 2)
    return k_des * (current_loading_mol_kg - q_eq)
