"""Coupled transient cycle simulation with mass and energy balances.

Simulates the continuous movement of the sorbent belt across adsorption,
regeneration, recovery, and cooling zones, coupled to rollers and the fluid loop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from dac_sim.belt import DiscretizedBelt
from dac_sim.fluid_loop import FluidLoop
from dac_sim.sorbent import (
    CO2_MOLAR_MASS_KG_MOL,
    SorbentProperties,
    adsorption_rate_mol_kg_s,
    desorption_rate_mol_kg_s,
)
from dac_sim.thermal import (
    ThermalNode,
    sensible_energy_change_j,
    temperature_step,
)


def _require_positive(name: str, value: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be a positive finite number.")


@dataclass
class CycleSimulationResult:
    """Complete results and balances from a coupled DAC cycle simulation."""

    # Time and state trajectories
    time_s: list[float]
    hot_roller_temp_k: list[float]
    recovery_roller_temp_k: list[float]
    cooling_roller_temp_k: list[float]
    mean_belt_temp_k: list[float]
    mean_belt_loading_mol_kg: list[float]

    # Mass balance quantities [kg CO2]
    co2_air_fed_kg: float
    co2_captured_kg: float
    co2_air_untreated_kg: float
    co2_released_kg: float
    co2_sorbent_initial_kg: float
    co2_sorbent_final_kg: float
    co2_sorbent_delta_kg: float
    mass_balance_residual_kg: float
    total_co2_balance_residual_kg: float

    # Energy balance quantities [J]
    heater_energy_j: float
    ambient_energy_j: float
    fluid_energy_j: float
    fluid_heat_recovered_j: float
    desorption_energy_j: float
    sensible_energy_change_j: float
    total_energy_input_j: float
    total_energy_absorbed_j: float
    energy_balance_residual_j: float

    # Engineering metrics
    duration_s: float
    capture_rate_g_h: float
    specific_thermal_energy_mj_kg: float
    specific_thermal_energy_mwh_t: float
    net_specific_thermal_energy_mj_kg: float
    heat_recovery_ratio: float


def run_cycle_simulation(
    belt: DiscretizedBelt,
    sorbent_props: SorbentProperties,
    duration_s: float,
    time_step_s: float = 0.1,
    heater_power_w: float = 500.0,
    fan_airflow_m3_h: float = 150.0,
    air_co2_concentration_g_m3: float = 0.72,
    ambient_temperature_k: float = 298.15,
    fluid_flow_l_min: float = 0.5,
    fluid_inlet_temperature_k: float = 310.0,
    hot_roller_mass_kg: float = 2.0,
    hot_roller_cp_j_kg_k: float = 500.0,
    hot_roller_temp_k: float = 378.15,
    recovery_roller_mass_kg: float = 1.0,
    recovery_roller_cp_j_kg_k: float = 4180.0,
    recovery_roller_temp_k: float = 338.15,
    cooling_roller_mass_kg: float = 2.0,
    cooling_roller_cp_j_kg_k: float = 500.0,
    cooling_roller_temp_k: float = 298.15,
    conductance_hot_belt_w_k: float = 15.0,
    conductance_recovery_belt_w_k: float = 10.0,
    conductance_cooling_belt_w_k: float = 12.0,
    ambient_loss_hot_roller_w_k: float = 2.0,
    ambient_loss_recovery_w_k: float = 1.0,
    ambient_loss_cooling_w_k: float = 2.0,
    ambient_loss_belt_per_segment_w_k: float = 0.05,
) -> CycleSimulationResult:
    """Run an auditable coupled transient simulation of the DAC belt system.

    Tracks CO2 mass balance and thermal energy conservation across explicit Euler steps.
    """
    _require_positive("duration_s", duration_s)
    _require_positive("time_step_s", time_step_s)
    _require_positive("fan_airflow_m3_h", fan_airflow_m3_h)
    _require_positive("air_co2_concentration_g_m3", air_co2_concentration_g_m3)
    _require_positive("ambient_temperature_k", ambient_temperature_k)

    # Initial states
    initial_co2_sorbent_kg = belt.total_co2_content_kg
    initial_belt_temps = [seg.temperature_k for seg in belt.segments]
    initial_hot_temp = hot_roller_temp_k
    initial_rec_temp = recovery_roller_temp_k
    initial_cool_temp = cooling_roller_temp_k

    # Fluid loop setup
    # 1 L/min water = 1/60 kg/s = 0.01667 kg/s
    fluid_m_dot_kg_s = (fluid_flow_l_min * 1.0) / 60.0
    fluid_cp = 4180.0
    fluid_loop = FluidLoop(
        node_name="recovery_roller",
        mass_flow_rate_kg_s=fluid_m_dot_kg_s,
        fluid_specific_heat_j_kg_k=fluid_cp,
        inlet_temperature_k=fluid_inlet_temperature_k,
    )

    # Air CO2 feed rate [kg/s]: (m3/h / 3600) * (g/m3 / 1000)
    co2_feed_rate_kg_s = (fan_airflow_m3_h / 3600.0) * (
        air_co2_concentration_g_m3 / 1000.0
    )

    # Integrators
    elapsed_s = 0.0
    cum_co2_air_fed_kg = 0.0
    cum_co2_captured_kg = 0.0
    cum_co2_untreated_kg = 0.0
    cum_co2_released_kg = 0.0

    cum_heater_energy_j = 0.0
    cum_ambient_energy_j = 0.0
    cum_fluid_energy_j = 0.0
    cum_desorption_energy_j = 0.0

    # History arrays
    hist_time_s = [0.0]
    hist_hot_k = [hot_roller_temp_k]
    hist_rec_k = [recovery_roller_temp_k]
    hist_cool_k = [cooling_roller_temp_k]
    hist_belt_k = [belt.mean_temperature_k]
    hist_loading = [belt.mean_loading_mol_kg]

    # Time integration loop
    while elapsed_s < duration_s:
        dt = min(time_step_s, duration_s - elapsed_s)

        # 1. CO2 in air fed during this step
        step_co2_air_in_kg = co2_feed_rate_kg_s * dt
        cum_co2_air_fed_kg += step_co2_air_in_kg

        # 2. Advance belt positions
        belt.advance_positions(dt)

        # 3. Identify segments in zones
        ads_segments = [s for s in belt.segments if belt.is_in_adsorption_zone(s.position_m)]
        hot_segments = [s for s in belt.segments if belt.is_in_regeneration_zone(s.position_m)]
        rec_segments = [s for s in belt.segments if belt.is_in_recovery_zone(s.position_m)]
        cool_segments = [s for s in belt.segments if belt.is_in_cooling_zone(s.position_m)]

        # 4. Adsorption in adsorption zone
        # Rate is limited by air CO2 supply
        step_potential_ads_mol = 0.0
        potential_ads_per_seg = {}
        for seg in ads_segments:
            r_ads = adsorption_rate_mol_kg_s(
                seg.loading_mol_kg, seg.temperature_k, sorbent_props
            )
            delta_mol = r_ads * dt * seg.sorbent_mass_kg
            potential_ads_per_seg[seg.index] = delta_mol
            step_potential_ads_mol += delta_mol

        step_potential_ads_kg = step_potential_ads_mol * CO2_MOLAR_MASS_KG_MOL
        if step_potential_ads_kg > 0:
            capture_fraction = min(1.0, step_co2_air_in_kg / step_potential_ads_kg)
        else:
            capture_fraction = 1.0

        step_co2_captured_kg = 0.0
        for seg in ads_segments:
            actual_delta_mol = potential_ads_per_seg[seg.index] * capture_fraction
            seg.loading_mol_kg += actual_delta_mol / seg.sorbent_mass_kg
            step_co2_captured_kg += actual_delta_mol * CO2_MOLAR_MASS_KG_MOL

        step_co2_untreated_kg = step_co2_air_in_kg - step_co2_captured_kg
        cum_co2_captured_kg += step_co2_captured_kg
        cum_co2_untreated_kg += step_co2_untreated_kg

        # 5. Desorption in regeneration zone
        step_co2_released_kg = 0.0
        for seg in hot_segments:
            r_des = desorption_rate_mol_kg_s(
                seg.loading_mol_kg, seg.temperature_k, sorbent_props
            )
            delta_mol = min(
                seg.loading_mol_kg * seg.sorbent_mass_kg,
                r_des * dt * seg.sorbent_mass_kg,
            )
            seg.loading_mol_kg -= delta_mol / seg.sorbent_mass_kg
            delta_kg = delta_mol * CO2_MOLAR_MASS_KG_MOL
            step_co2_released_kg += delta_kg

        cum_co2_released_kg += step_co2_released_kg
        step_desorption_energy_j = (
            step_co2_released_kg * sorbent_props.desorption_heat_j_kg
        )
        cum_desorption_energy_j += step_desorption_energy_j

        # 6. Thermal integration
        # Distribute contact conductances among segments in contact
        n_hot = max(1, len(hot_segments))
        n_rec = max(1, len(rec_segments))
        n_cool = max(1, len(cool_segments))

        g_hot_seg = conductance_hot_belt_w_k / n_hot
        g_rec_seg = conductance_recovery_belt_w_k / n_rec
        g_cool_seg = conductance_cooling_belt_w_k / n_cool

        # Net heat rates on nodes
        q_hot_roller_w = heater_power_w
        q_rec_roller_w = 0.0
        q_cool_roller_w = 0.0

        # Ambient exchanges
        q_amb_hot_w = ambient_loss_hot_roller_w_k * (ambient_temperature_k - hot_roller_temp_k)
        q_amb_rec_w = ambient_loss_recovery_w_k * (ambient_temperature_k - recovery_roller_temp_k)
        q_amb_cool_w = ambient_loss_cooling_w_k * (ambient_temperature_k - cooling_roller_temp_k)

        q_hot_roller_w += q_amb_hot_w
        q_rec_roller_w += q_amb_rec_w
        q_cool_roller_w += q_amb_cool_w

        # Fluid exchange on recovery roller
        q_fluid_w = fluid_loop.heat_rate_to_node_w(recovery_roller_temp_k)
        q_rec_roller_w += q_fluid_w

        # Ambient exchange on belt segments
        step_amb_belt_energy_j = 0.0
        for seg in belt.segments:
            q_amb_seg = ambient_loss_belt_per_segment_w_k * (
                ambient_temperature_k - seg.temperature_k
            )
            seg.temperature_k += (q_amb_seg * dt) / seg.heat_capacity_j_k
            step_amb_belt_energy_j += q_amb_seg * dt

        # Contact heat exchange between rollers and belt segments
        for seg in hot_segments:
            q_contact = g_hot_seg * (hot_roller_temp_k - seg.temperature_k)
            q_hot_roller_w -= q_contact
            seg.temperature_k += (q_contact * dt) / seg.heat_capacity_j_k

        for seg in rec_segments:
            q_contact = g_rec_seg * (seg.temperature_k - recovery_roller_temp_k)
            q_rec_roller_w += q_contact
            seg.temperature_k -= (q_contact * dt) / seg.heat_capacity_j_k

        for seg in cool_segments:
            q_contact = g_cool_seg * (seg.temperature_k - cooling_roller_temp_k)
            q_cool_roller_w += q_contact
            seg.temperature_k -= (q_contact * dt) / seg.heat_capacity_j_k

        # Subtract desorption heat from hot roller
        # Desorption absorbs heat from the hot roller contact
        desorption_power_w = step_desorption_energy_j / dt
        q_hot_roller_w -= desorption_power_w

        # Step roller temperatures
        hot_roller_temp_k = temperature_step(
            hot_roller_temp_k,
            hot_roller_mass_kg,
            hot_roller_cp_j_kg_k,
            q_hot_roller_w,
            dt,
        )
        recovery_roller_temp_k = temperature_step(
            recovery_roller_temp_k,
            recovery_roller_mass_kg,
            recovery_roller_cp_j_kg_k,
            q_rec_roller_w,
            dt,
        )
        cooling_roller_temp_k = temperature_step(
            cooling_roller_temp_k,
            cooling_roller_mass_kg,
            cooling_roller_cp_j_kg_k,
            q_cool_roller_w,
            dt,
        )

        # Accumulate energies
        cum_heater_energy_j += heater_power_w * dt
        cum_ambient_energy_j += (
            (q_amb_hot_w + q_amb_rec_w + q_amb_cool_w) * dt
            + step_amb_belt_energy_j
        )
        cum_fluid_energy_j += q_fluid_w * dt

        elapsed_s += dt
        hist_time_s.append(elapsed_s)
        hist_hot_k.append(hot_roller_temp_k)
        hist_rec_k.append(recovery_roller_temp_k)
        hist_cool_k.append(cooling_roller_temp_k)
        hist_belt_k.append(belt.mean_temperature_k)
        hist_loading.append(belt.mean_loading_mol_kg)

    # Final calculations and balances
    final_co2_sorbent_kg = belt.total_co2_content_kg
    co2_sorbent_delta_kg = final_co2_sorbent_kg - initial_co2_sorbent_kg

    # Mass balance residual: Sorbent CO2 in - out - accumulated = 0
    mass_balance_residual_kg = (
        cum_co2_captured_kg - cum_co2_released_kg - co2_sorbent_delta_kg
    )
    # Total CO2 balance: Air in - (Air untreated + Released + Sorbent accumulation) = 0
    total_co2_balance_residual_kg = (
        cum_co2_air_fed_kg
        - (cum_co2_untreated_kg + cum_co2_released_kg + co2_sorbent_delta_kg)
    )

    # Sensible energy changes across all thermal components [J]
    delta_sensible_hot = sensible_energy_change_j(
        hot_roller_mass_kg, hot_roller_cp_j_kg_k, initial_hot_temp, hot_roller_temp_k
    )
    delta_sensible_rec = sensible_energy_change_j(
        recovery_roller_mass_kg,
        recovery_roller_cp_j_kg_k,
        initial_rec_temp,
        recovery_roller_temp_k,
    )
    delta_sensible_cool = sensible_energy_change_j(
        cooling_roller_mass_kg,
        cooling_roller_cp_j_kg_k,
        initial_cool_temp,
        cooling_roller_temp_k,
    )
    delta_sensible_belt = sum(
        sensible_energy_change_j(
            seg.total_mass_kg,
            seg.specific_heat_j_kg_k,
            t_init,
            seg.temperature_k,
        )
        for seg, t_init in zip(belt.segments, initial_belt_temps)
    )
    total_sensible_change_j = (
        delta_sensible_hot
        + delta_sensible_rec
        + delta_sensible_cool
        + delta_sensible_belt
    )

    total_energy_input_j = (
        cum_heater_energy_j + cum_ambient_energy_j + cum_fluid_energy_j
    )
    total_energy_absorbed_j = (
        total_sensible_change_j + cum_desorption_energy_j
    )
    energy_balance_residual_j = (
        total_energy_absorbed_j - total_energy_input_j
    )

    # Performance metrics
    capture_rate_g_h = (
        (cum_co2_captured_kg * 1000.0) / (duration_s / 3600.0)
        if duration_s > 0
        else 0.0
    )

    fluid_recovered_j = -cum_fluid_energy_j
    net_thermal_input_j = cum_heater_energy_j - max(0.0, fluid_recovered_j)

    if cum_co2_captured_kg > 0:
        spec_energy_mj_kg = (cum_heater_energy_j / 1e6) / cum_co2_captured_kg
        net_spec_energy_mj_kg = (net_thermal_input_j / 1e6) / cum_co2_captured_kg
        spec_energy_mwh_t = (cum_heater_energy_j / 3.6e9) / (cum_co2_captured_kg / 1000.0)
    else:
        spec_energy_mj_kg = 0.0
        net_spec_energy_mj_kg = 0.0
        spec_energy_mwh_t = 0.0

    heat_recovery_ratio = (
        fluid_recovered_j / cum_heater_energy_j
        if cum_heater_energy_j > 0
        else 0.0
    )

    return CycleSimulationResult(
        time_s=hist_time_s,
        hot_roller_temp_k=hist_hot_k,
        recovery_roller_temp_k=hist_rec_k,
        cooling_roller_temp_k=hist_cool_k,
        mean_belt_temp_k=hist_belt_k,
        mean_belt_loading_mol_kg=hist_loading,
        co2_air_fed_kg=cum_co2_air_fed_kg,
        co2_captured_kg=cum_co2_captured_kg,
        co2_air_untreated_kg=cum_co2_untreated_kg,
        co2_released_kg=cum_co2_released_kg,
        co2_sorbent_initial_kg=initial_co2_sorbent_kg,
        co2_sorbent_final_kg=final_co2_sorbent_kg,
        co2_sorbent_delta_kg=co2_sorbent_delta_kg,
        mass_balance_residual_kg=mass_balance_residual_kg,
        total_co2_balance_residual_kg=total_co2_balance_residual_kg,
        heater_energy_j=cum_heater_energy_j,
        ambient_energy_j=cum_ambient_energy_j,
        fluid_energy_j=cum_fluid_energy_j,
        fluid_heat_recovered_j=fluid_recovered_j,
        desorption_energy_j=cum_desorption_energy_j,
        sensible_energy_change_j=total_sensible_change_j,
        total_energy_input_j=total_energy_input_j,
        total_energy_absorbed_j=total_energy_absorbed_j,
        energy_balance_residual_j=energy_balance_residual_j,
        duration_s=duration_s,
        capture_rate_g_h=capture_rate_g_h,
        specific_thermal_energy_mj_kg=spec_energy_mj_kg,
        specific_thermal_energy_mwh_t=spec_energy_mwh_t,
        net_specific_thermal_energy_mj_kg=net_spec_energy_mj_kg,
        heat_recovery_ratio=heat_recovery_ratio,
    )
