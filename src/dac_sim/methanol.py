"""Downstream methanol synthesis assessment and mass-energy balance module.

Models the catalytic hydrogenation of DAC-captured CO2 into e-methanol:
    CO2 + 3 H2 <==> CH3OH + H2O  (Delta H_298 = -49.5 kJ/mol)

Accounts for stoichiometric consumption, hydrogen supply via water electrolysis,
compression energy, reaction heat release, and gas conditioning requirements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from dac_sim.sorbent import CO2_MOLAR_MASS_G_MOL

METHANOL_MOLAR_MASS_G_MOL = 32.042
H2_MOLAR_MASS_G_MOL = 2.016
H2O_MOLAR_MASS_G_MOL = 18.015

# Enthalpy of reaction at 298 K for CO2 + 3 H2 -> CH3OH + H2O: -49.5 kJ/mol
DELTA_H_RXN_J_MOL_METHANOL = -49.5e3

# Lower heating value of hydrogen: 120.0 MJ/kg = 33.33 kWh/kg
H2_LHV_MJ_KG = 120.0
H2_LHV_MWH_T = 33.333


def _require_positive(name: str, value: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be a positive finite number.")


@dataclass(frozen=True)
class MethanolProcessConfig:
    """Design and operating parameters for CO2 hydrogenation to methanol.

    Attributes:
        operating_pressure_bar: Synthesis loop pressure [bar]. Typical: 50-80 bar.
        operating_temperature_c: Catalyst bed temperature [C]. Typical: 220-260 C.
        co2_single_pass_conversion: Fraction of CO2 converted per pass.
            Typical 0.20-0.35; overall conversion > 0.95 with recycle.
        overall_conversion_efficiency: Total CO2 utilization with gas recycle.
            Default 0.95 (95%).
        electrolyzer_efficiency_lhv: Electrolyzer stack efficiency relative to LHV.
            Typical PEM / Alkaline: 0.65 - 0.72. Default 0.68.
        compressor_isentropic_efficiency: Compressor isentropic efficiency.
            Default 0.75.
        reactor_heat_recovery_fraction: Fraction of exothermic reaction heat
            recovered for reuse (e.g. DAC desorption or district heat).
            Default 0.60.
    """

    operating_pressure_bar: float = 60.0
    operating_temperature_c: float = 240.0
    overall_conversion_efficiency: float = 0.95
    electrolyzer_efficiency_lhv: float = 0.68
    compressor_isentropic_efficiency: float = 0.75
    reactor_heat_recovery_fraction: float = 0.60

    def __post_init__(self) -> None:
        for field in (
            "operating_pressure_bar",
            "operating_temperature_c",
            "overall_conversion_efficiency",
            "electrolyzer_efficiency_lhv",
            "compressor_isentropic_efficiency",
            "reactor_heat_recovery_fraction",
        ):
            _require_positive(field, getattr(self, field))

        if not (0.0 < self.overall_conversion_efficiency <= 1.0):
            raise ValueError("overall_conversion_efficiency must be in (0, 1].")
        if not (0.0 < self.electrolyzer_efficiency_lhv <= 1.0):
            raise ValueError("electrolyzer_efficiency_lhv must be in (0, 1].")
        if not (0.0 < self.reactor_heat_recovery_fraction <= 1.0):
            raise ValueError("reactor_heat_recovery_fraction must be in (0, 1].")


@dataclass
class MethanolProductionEstimate:
    """Stoichiometric, energetic, and mass metrics for methanol synthesis."""

    co2_feed_kg_h: float
    methanol_produced_kg_h: float
    water_byproduct_kg_h: float
    h2_demand_kg_h: float
    electrolysis_power_kw: float
    electrolysis_energy_mwh_t_methanol: float
    compression_power_kw: float
    exothermic_heat_generated_kw: float
    recoverable_heat_kw: float
    recoverable_heat_mwh_t_co2: float
    stoichiometric_co2_ratio_t_t: float


def evaluate_methanol_production(
    co2_feed_rate_kg_h: float,
    config: MethanolProcessConfig | None = None,
) -> MethanolProductionEstimate:
    """Evaluate downstream methanol production from a known DAC CO2 capture stream."""
    _require_positive("co2_feed_rate_kg_h", co2_feed_rate_kg_h)
    cfg = config if config is not None else MethanolProcessConfig()

    # Stoichiometry: CO2 + 3 H2 -> CH3OH + H2O
    # 44.01 g CO2 + 6.048 g H2 -> 32.042 g CH3OH + 18.015 g H2O
    # Stoichiometric ratio: 44.0095 / 32.042 = 1.3735 kg CO2 / kg CH3OH
    theoretical_co2_per_methanol = CO2_MOLAR_MASS_G_MOL / METHANOL_MOLAR_MASS_G_MOL
    actual_co2_per_methanol = (
        theoretical_co2_per_methanol / cfg.overall_conversion_efficiency
    )

    methanol_produced_kg_h = co2_feed_rate_kg_h / actual_co2_per_methanol
    co2_converted_kg_h = co2_feed_rate_kg_h * cfg.overall_conversion_efficiency

    # Moles of methanol produced per hour
    moles_methanol_h = (methanol_produced_kg_h * 1000.0) / METHANOL_MOLAR_MASS_G_MOL

    # H2 consumption: 3 moles H2 per mole methanol
    moles_h2_h = moles_methanol_h * 3.0
    h2_demand_kg_h = (moles_h2_h * H2_MOLAR_MASS_G_MOL) / 1000.0

    # Water byproduct: 1 mole H2O per mole methanol
    water_byproduct_kg_h = (moles_methanol_h * H2O_MOLAR_MASS_G_MOL) / 1000.0

    # Electrolysis power: H2 LHV / efficiency
    # H2 energy: h2_demand_kg_h * 33.333 kWh/kg = kWh/h = kW
    h2_energy_kw = h2_demand_kg_h * (H2_LHV_MJ_KG / 3.6)
    electrolysis_power_kw = h2_energy_kw / cfg.electrolyzer_efficiency_lhv
    electrolysis_mwh_t_methanol = (
        (electrolysis_power_kw / (methanol_produced_kg_h / 1000.0)) / 1000.0
        if methanol_produced_kg_h > 0
        else 0.0
    )

    # CO2 & H2 Compression work from 1 bar to operating pressure (isentropic approx)
    # W_isen = (gamma/(gamma-1)) * R * T * ((P2/P1)^((gamma-1)/gamma) - 1)
    # Approximate specific compression work for syngas mix to 60 bar: ~0.8 MJ/kg feed
    total_gas_feed_kg_h = co2_feed_rate_kg_h + h2_demand_kg_h
    compression_specific_kwh_kg = 0.25 * math.log(cfg.operating_pressure_bar / 1.0) / math.log(60.0)
    compression_power_kw = total_gas_feed_kg_h * compression_specific_kwh_kg

    # Exothermic reaction heat release: -49.5 kJ/mol CH3OH
    # Heat generated [kW] = moles_methanol_h * 49.5e3 J / 3600 s / 1000
    heat_generated_kw = (moles_methanol_h * abs(DELTA_H_RXN_J_MOL_METHANOL)) / 3.6e6
    recoverable_heat_kw = heat_generated_kw * cfg.reactor_heat_recovery_fraction
    recoverable_heat_mwh_t_co2 = (
        (recoverable_heat_kw / (co2_feed_rate_kg_h / 1000.0)) / 1000.0
        if co2_feed_rate_kg_h > 0
        else 0.0
    )

    return MethanolProductionEstimate(
        co2_feed_kg_h=co2_feed_rate_kg_h,
        methanol_produced_kg_h=methanol_produced_kg_h,
        water_byproduct_kg_h=water_byproduct_kg_h,
        h2_demand_kg_h=h2_demand_kg_h,
        electrolysis_power_kw=electrolysis_power_kw,
        electrolysis_energy_mwh_t_methanol=electrolysis_mwh_t_methanol,
        compression_power_kw=compression_power_kw,
        exothermic_heat_generated_kw=heat_generated_kw,
        recoverable_heat_kw=recoverable_heat_kw,
        recoverable_heat_mwh_t_co2=recoverable_heat_mwh_t_co2,
        stoichiometric_co2_ratio_t_t=actual_co2_per_methanol,
    )
