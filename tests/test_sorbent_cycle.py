"""Tests for sorbent kinetics, belt discretization, and complete cycle mass/energy balances."""

import pytest
import yaml
from pathlib import Path

from dac_sim.sorbent import (
    CO2_MOLAR_MASS_KG_MOL,
    SorbentProperties,
    equilibrium_capacity_mol_kg,
    adsorption_rate_mol_kg_s,
    desorption_rate_mol_kg_s,
)
from dac_sim.belt import DiscretizedBelt, BeltSegment, BeltZoneLayout
from dac_sim.cycle import run_cycle_simulation, CycleSimulationResult, HeaterController


@pytest.fixture
def assumptions_data():
    with Path("assumptions.yaml").open(encoding="utf-8-sig") as f:
        return yaml.safe_load(f)


def test_sorbent_properties_defaults_and_validation(assumptions_data):
    props = SorbentProperties()
    assert props.working_capacity_mol_kg == pytest.approx(1.0)
    assert props.uptake_rate_mol_kg_s == pytest.approx(0.065 / 60.0)
    assert props.max_loading_kg_co2_kg_sorbent == pytest.approx(
        CO2_MOLAR_MASS_KG_MOL
    )

    # From assumptions register
    loaded_props = SorbentProperties.from_assumptions(assumptions_data)
    assert loaded_props.working_capacity_mol_kg == pytest.approx(1.0)
    assert loaded_props.desorption_temp_peak_k == pytest.approx(378.15)

    # Error handling
    with pytest.raises(ValueError):
        SorbentProperties(working_capacity_mol_kg=-1.0)
    with pytest.raises(ValueError):
        SorbentProperties(desorption_temp_peak_k=300.0, desorption_temp_onset_k=350.0)
    with pytest.raises(ValueError):
        SorbentProperties(residual_capacity_fraction=1.5)


def test_equilibrium_capacity_temperature_dependency():
    props = SorbentProperties()
    # At room temperature: capacity is high (~ 1.0 mol/kg)
    q_ambient = equilibrium_capacity_mol_kg(298.15, props)
    assert q_ambient > 0.95

    # At desorption peak (105 C / 378.15 K): capacity is near residual (~ 0.05 mol/kg)
    q_hot = equilibrium_capacity_mol_kg(378.15, props)
    assert q_hot < 0.20
    assert q_hot > 0.04
    assert q_ambient > q_hot


def test_adsorption_kinetics():
    props = SorbentProperties()
    # Clean sorbent at ambient: positive adsorption rate
    r1 = adsorption_rate_mol_kg_s(0.0, 298.15, props)
    assert r1 > 0.0

    # Partially loaded: lower driving force -> lower rate
    r2 = adsorption_rate_mol_kg_s(0.5, 298.15, props)
    assert 0 < r2 < r1

    # Saturated sorbent: zero rate
    r_sat = adsorption_rate_mol_kg_s(1.0, 298.15, props)
    assert r_sat == pytest.approx(0.0)


def test_desorption_kinetics():
    props = SorbentProperties()
    # At ambient: no thermal desorption
    r_cold = desorption_rate_mol_kg_s(0.8, 298.15, props)
    assert r_cold == pytest.approx(0.0)

    # Above onset at 360 K: desorption is active
    r_warm = desorption_rate_mol_kg_s(0.8, 360.0, props)
    assert r_warm > 0.0

    # At hot roller temp 378 K: faster desorption
    r_hot = desorption_rate_mol_kg_s(0.8, 378.15, props)
    assert r_hot > r_warm


def test_discretized_belt_geometry(assumptions_data):
    belt = DiscretizedBelt.from_assumptions(assumptions_data, num_segments=66)
    assert len(belt.segments) == 66
    assert belt.loop_length_m == pytest.approx(1.98)
    assert belt.usable_width_m == pytest.approx(0.18)

    # Sorbent mass check: 1.98 * 0.18 * 0.3 kg/m2 = 0.10692 kg
    assert belt.total_sorbent_mass_kg == pytest.approx(0.10692, rel=1e-3)

    # Advance positions around loop
    initial_p0 = belt.segments[0].position_m
    belt.advance_positions(10.0)  # 10s * 0.002 m/s = 0.02 m
    assert belt.segments[0].position_m == pytest.approx(initial_p0 + 0.02)


def test_cycle_simulation_mass_and_energy_conservation(assumptions_data):
    belt = DiscretizedBelt.from_assumptions(
        assumptions_data, num_segments=40, initial_temperature_k=298.15, initial_loading_mol_kg=0.1
    )
    props = SorbentProperties.from_assumptions(assumptions_data)

    result = run_cycle_simulation(
        belt=belt,
        sorbent_props=props,
        duration_s=20.0,
        time_step_s=0.1,
        heater_power_w=500.0,
        fan_airflow_m3_h=150.0,
        air_co2_concentration_g_m3=0.72,
        ambient_temperature_k=298.15,
        fluid_flow_l_min=0.5,
        fluid_inlet_temperature_k=305.0,
    )

    # CO2 Mass balances
    assert result.mass_balance_residual_kg == pytest.approx(0.0, abs=1e-12)
    assert result.total_co2_balance_residual_kg == pytest.approx(0.0, abs=1e-12)
    assert result.co2_air_fed_kg > 0.0
    assert result.co2_captured_kg > 0.0
    assert result.co2_air_untreated_kg >= 0.0

    # Energy balance
    assert result.energy_balance_residual_j == pytest.approx(0.0, abs=1e-8)
    assert result.heater_energy_j > 0.0
    assert result.heater_energy_j == pytest.approx(
        result.average_heater_power_w * result.duration_s, rel=1e-6
    )
    assert result.total_energy_absorbed_j == pytest.approx(
        result.total_energy_input_j, abs=1e-8
    )

    # Performance metrics
    assert result.capture_rate_g_h > 0.0
    assert result.specific_thermal_energy_mj_kg > 0.0
    assert result.specific_thermal_energy_mwh_t > 0.0
    assert len(result.heater_power_w) == len(result.time_s)


def test_cycle_simulation_constant_heater_mode(assumptions_data):
    belt = DiscretizedBelt.from_assumptions(
        assumptions_data, num_segments=30, initial_temperature_k=298.15, initial_loading_mol_kg=0.1
    )
    props = SorbentProperties.from_assumptions(assumptions_data)

    result = run_cycle_simulation(
        belt=belt,
        sorbent_props=props,
        duration_s=20.0,
        time_step_s=0.1,
        heater_power_w=500.0,
        heater_controller="constant",
    )

    # In constant mode, heater delivers exactly 500 W for 20 s = 10,000 J
    assert result.heater_energy_j == pytest.approx(500.0 * 20.0)
    assert result.energy_balance_residual_j == pytest.approx(0.0, abs=1e-8)
    assert result.average_heater_power_w == pytest.approx(500.0)


def test_heater_controller_unit():
    # Validation errors
    with pytest.raises(ValueError):
        HeaterController(target_temp_k=-10.0)
    with pytest.raises(ValueError):
        HeaterController(max_power_w=0.0)
    with pytest.raises(ValueError):
        HeaterController(mode="invalid_mode")
    with pytest.raises(ValueError):
        HeaterController(deadband_k=-1.0)
    with pytest.raises(ValueError):
        HeaterController(kp=-5.0)

    # Constant mode
    ctrl_const = HeaterController(max_power_w=500.0, mode="constant")
    assert ctrl_const.compute_power_w(350.0, 0.1) == 500.0
    assert ctrl_const.compute_power_w(400.0, 0.1) == 500.0

    # Thermostat mode with deadband
    ctrl_thermo = HeaterController(target_temp_k=378.15, max_power_w=500.0, mode="thermostat", deadband_k=1.0)
    # Cold: full power
    assert ctrl_thermo.compute_power_w(375.0, 0.1) == 500.0
    # In deadband from below: stays ON
    assert ctrl_thermo.compute_power_w(378.0, 0.1) == 500.0
    # Over target + deadband (> 379.15): turns OFF
    assert ctrl_thermo.compute_power_w(379.5, 0.1) == 0.0
    # In deadband from above: stays OFF
    assert ctrl_thermo.compute_power_w(378.0, 0.1) == 0.0
    # Drops below target - deadband (< 377.15): turns ON
    assert ctrl_thermo.compute_power_w(377.0, 0.1) == 500.0

    # Proportional mode
    ctrl_prop = HeaterController(target_temp_k=378.15, max_power_w=500.0, mode="proportional", kp=50.0)
    # Error = 2 K -> 100 W
    assert ctrl_prop.compute_power_w(376.15, 0.1) == pytest.approx(100.0)
    # Error = 20 K -> 1000 W capped at 500 W
    assert ctrl_prop.compute_power_w(358.15, 0.1) == 500.0
    # At or above target -> 0 W
    assert ctrl_prop.compute_power_w(378.15, 0.1) == 0.0
    assert ctrl_prop.compute_power_w(380.15, 0.1) == 0.0


def test_hot_roller_temperature_control_990s(assumptions_data):
    """Verify hot roller maintains 105 C (378.15 K) without unphysical runaway over a full 990s cycle."""
    belt = DiscretizedBelt.from_assumptions(
        assumptions_data, num_segments=40, initial_temperature_k=298.15, initial_loading_mol_kg=0.08
    )
    props = SorbentProperties.from_assumptions(assumptions_data)

    # PID control
    result_pid = run_cycle_simulation(
        belt=belt,
        sorbent_props=props,
        duration_s=990.0,
        time_step_s=0.1,
        heater_controller="pid",
        target_hot_roller_temp_k=378.15,
        heater_power_w=500.0,
    )

    # Roller temperature must stay near 105 C and NOT exceed 106 C (no runaway to 218 C)
    assert result_pid.max_hot_roller_temp_k < 379.0  # < 105.85 C
    assert result_pid.temperature_overshoot_k < 0.5   # < 0.5 K overshoot
    assert result_pid.hot_roller_temp_k[-1] == pytest.approx(378.15, abs=0.5)
    # Average power should reflect ~180-200 W steady loss rather than 500 W
    assert 170.0 < result_pid.average_heater_power_w < 210.0
    # Gross specific energy drops from ~205 MWh/t to realistic bench ~75-85 MWh/t
    assert 70.0 < result_pid.specific_thermal_energy_mwh_t < 90.0
    # Energy balance strictly closed
    assert result_pid.energy_balance_residual_j == pytest.approx(0.0, abs=1e-8)
    assert result_pid.mass_balance_residual_kg == pytest.approx(0.0, abs=1e-12)


def test_time_step_independence(assumptions_data):
    """Verify simulation is insensitive to time-step reduction (dt=0.1 vs dt=0.05)."""
    props = SorbentProperties.from_assumptions(assumptions_data)

    belt1 = DiscretizedBelt.from_assumptions(assumptions_data, num_segments=30)
    res_dt1 = run_cycle_simulation(belt1, props, duration_s=100.0, time_step_s=0.1)

    belt2 = DiscretizedBelt.from_assumptions(assumptions_data, num_segments=30)
    res_dt2 = run_cycle_simulation(belt2, props, duration_s=100.0, time_step_s=0.05)

    # Capture rates and average powers should match within 0.1%
    assert res_dt1.capture_rate_g_h == pytest.approx(res_dt2.capture_rate_g_h, rel=1e-3)
    assert res_dt1.average_heater_power_w == pytest.approx(res_dt2.average_heater_power_w, rel=5e-3)
    assert res_dt1.energy_balance_residual_j == pytest.approx(0.0, abs=1e-8)
    assert res_dt2.energy_balance_residual_j == pytest.approx(0.0, abs=1e-8)
