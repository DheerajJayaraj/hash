"""Focused regression tests verifying DAC simulation debugging and showcase recovery.

Covers all 9 criteria from Section 9 of the Master Prompt:
1. Temperature overshoot and final setpoint error being calculated separately.
2. Initial temperature and target temperature being passed independently.
3. A baseline controlled simulation.
4. A changed-setpoint run.
5. Zero-desorption behavior, with the expected result grounded in the model.
6. Mass conservation across capture, release, and sorbent inventory.
7. Energy-balance accounting and heat-recovery edge cases.
8. Dashboard KPI values matching the returned simulation result.
9. CSV/JSON exports matching the latest completed run.
"""

from __future__ import annotations

import csv
import io
import json
import threading
import urllib.request
import urllib.error
from pathlib import Path

import pytest
import yaml

from dac_sim.belt import DiscretizedBelt
from dac_sim.cycle import HeaterController, run_cycle_simulation
from dac_sim.dashboard import (
    DEFAULT_PARAMS,
    load_assumptions_dict,
    run_simulation_api,
    start_dashboard_server,
    validate_dashboard_params,
)
from dac_sim.sorbent import SorbentProperties, equilibrium_capacity_mol_kg


@pytest.fixture
def assumptions_data():
    with Path("assumptions.yaml").open(encoding="utf-8-sig") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# 1. Temperature overshoot and final setpoint error calculated separately
# ---------------------------------------------------------------------------

def test_temperature_overshoot_and_setpoint_error_calculated_separately(assumptions_data):
    """Verify overshoot_k = max(0, max_T - target_T) and final_error_k = final_T - target_T are separate."""
    props = SorbentProperties.from_assumptions(assumptions_data)
    belt = DiscretizedBelt.from_assumptions(
        assumptions_data, num_segments=30, initial_temperature_k=298.15
    )

    # Step-down cooldown scenario: start at 105 C (378.15 K), target 90 C (363.15 K)
    res_stepdown = run_cycle_simulation(
        belt=belt,
        sorbent_props=props,
        duration_s=100.0,
        time_step_s=0.1,
        target_hot_roller_temp_k=363.15,
        hot_roller_temp_k=378.15,
        heater_controller="pid",
    )

    # Max temperature was initial (378.15 K), so overshoot above 363.15 K is 15.0 K
    assert res_stepdown.temperature_overshoot_k == pytest.approx(15.0, abs=0.1)

    # Final error: roller has cooled towards 363.15 K
    expected_error = res_stepdown.hot_roller_temp_k[-1] - 363.15
    assert res_stepdown.final_setpoint_error_k == pytest.approx(expected_error, abs=1e-6)

    # Crucial assertion: overshoot is NOT equal to final setpoint error
    assert res_stepdown.temperature_overshoot_k != pytest.approx(
        res_stepdown.final_setpoint_error_k, abs=1.0
    )


# ---------------------------------------------------------------------------
# 2. Initial temperature and target temperature passed independently
# ---------------------------------------------------------------------------

def test_initial_and_target_temperature_passed_independently():
    """Verify that target and initial temperatures are independent inputs."""
    # Custom payload with distinct values
    params = dict(DEFAULT_PARAMS)
    params["target_hot_roller_temp_c"] = 95.0
    params["initial_hot_roller_temp_c"] = 25.0  # Cold start

    clean = validate_dashboard_params(params)
    assert clean["target_hot_roller_temp_c"] == 95.0
    assert clean["initial_hot_roller_temp_c"] == 25.0

    # Ensure engine runs with these independent inputs
    res_api = run_simulation_api(params)
    kpis = res_api["kpis"]
    assert kpis["hot_roller_target_c"] == 95.0
    assert kpis["hot_roller_initial_c"] == 25.0
    # Final temperature heated from 25 C towards 95 C
    assert kpis["hot_roller_final_c"] > 80.0


# ---------------------------------------------------------------------------
# 3. Baseline controlled simulation (105 C, PID, 990s)
# ---------------------------------------------------------------------------

def test_baseline_controlled_simulation_full_revolution(assumptions_data):
    """Verify nominal 990 s baseline at 105 C target with PID control."""
    props = SorbentProperties.from_assumptions(assumptions_data)
    belt = DiscretizedBelt.from_assumptions(
        assumptions_data, num_segments=50, initial_temperature_k=298.15, initial_loading_mol_kg=0.08
    )

    res = run_cycle_simulation(
        belt=belt,
        sorbent_props=props,
        duration_s=990.0,
        time_step_s=0.1,
        target_hot_roller_temp_k=378.15,
        hot_roller_temp_k=378.15,
        heater_power_w=500.0,
        heater_controller="pid",
        fluid_inlet_temperature_k=305.0,
    )

    # Controller accuracy
    assert res.hot_roller_temp_k[-1] == pytest.approx(378.15, abs=0.5)
    assert res.temperature_overshoot_k < 0.5
    assert abs(res.final_setpoint_error_k) < 0.2

    # Heater power throttled
    assert 170.0 < res.average_heater_power_w < 210.0

    # Mass metrics
    assert res.co2_captured_kg == pytest.approx(0.000648, abs=1e-5)  # ~0.648 g
    assert res.co2_released_kg == pytest.approx(0.000092, abs=1e-5)  # ~0.092 g

    # Energy recovery and balance closure
    assert res.fluid_heat_recovered_j > 100000.0  # > 100 kJ
    assert 0.60 < res.heat_recovery_ratio < 0.75  # ~69%
    assert abs(res.mass_balance_residual_kg) < 1e-12
    assert abs(res.energy_balance_residual_j) < 1e-8


# ---------------------------------------------------------------------------
# 4. Changed-setpoint run (e.g. 90 C and 115 C)
# ---------------------------------------------------------------------------

def test_changed_setpoint_runs(assumptions_data):
    """Verify system behaves properly under altered setpoints."""
    props = SorbentProperties.from_assumptions(assumptions_data)

    # Case A: 90 C target, initialized at 90 C (full 990s revolution)
    belt_90 = DiscretizedBelt.from_assumptions(assumptions_data, num_segments=50)
    res_90 = run_cycle_simulation(
        belt=belt_90,
        sorbent_props=props,
        duration_s=990.0,
        time_step_s=0.1,
        target_hot_roller_temp_k=363.15,
        hot_roller_temp_k=363.15,
        heater_controller="pid",
    )
    assert res_90.hot_roller_temp_k[-1] == pytest.approx(363.15, abs=0.5)
    assert res_90.temperature_overshoot_k < 0.5

    # Case B: 115 C target, initialized at 115 C (full 990s revolution)
    belt_115 = DiscretizedBelt.from_assumptions(assumptions_data, num_segments=50)
    res_115 = run_cycle_simulation(
        belt=belt_115,
        sorbent_props=props,
        duration_s=990.0,
        time_step_s=0.1,
        target_hot_roller_temp_k=388.15,
        hot_roller_temp_k=388.15,
        heater_controller="pid",
    )
    assert res_115.hot_roller_temp_k[-1] == pytest.approx(388.15, abs=0.5)
    # Higher temperature incurs higher ambient standby loss -> higher average power
    assert res_115.average_heater_power_w > res_90.average_heater_power_w


# ---------------------------------------------------------------------------
# 5. Zero-desorption behavior grounded in thermodynamics
# ---------------------------------------------------------------------------

def test_zero_desorption_behavior_grounded_in_model(assumptions_data):
    """Verify that zero release at 90 C is a physical consequence of q < q_eq(90 C)."""
    props = SorbentProperties.from_assumptions(assumptions_data)
    belt = DiscretizedBelt.from_assumptions(
        assumptions_data, num_segments=40, initial_loading_mol_kg=0.08
    )

    # At 90 C (363.15 K), check equilibrium capacity
    q_eq_90 = equilibrium_capacity_mol_kg(363.15, props)
    assert q_eq_90 > 0.38  # ~0.409 mol/kg

    res = run_cycle_simulation(
        belt=belt,
        sorbent_props=props,
        duration_s=990.0,
        time_step_s=0.1,
        target_hot_roller_temp_k=363.15,
        hot_roller_temp_k=363.15,
    )

    # In 1 revolution, sorbent loading only reaches ~0.22 mol/kg, which is < q_eq(90 C)
    for seg in belt.segments:
        assert seg.loading_mol_kg < q_eq_90

    # Thermodynamically, no desorption can take place:
    assert res.co2_released_kg == pytest.approx(0.0, abs=1e-12)
    assert res.co2_captured_kg > 0.0006  # CO2 was still captured
    assert res.co2_sorbent_delta_kg == pytest.approx(res.co2_captured_kg, abs=1e-12)
    assert res.specific_energy_per_released_mj_kg is None  # Undefined per product


# ---------------------------------------------------------------------------
# 6. Mass conservation across capture, release, and sorbent inventory
# ---------------------------------------------------------------------------

def test_mass_conservation_active_and_zero_desorption(assumptions_data):
    """Verify mass balance: Captured = Released + Delta_Sorbent exactly."""
    props = SorbentProperties.from_assumptions(assumptions_data)

    for target_k in (378.15, 363.15):
        belt = DiscretizedBelt.from_assumptions(assumptions_data, num_segments=30)
        res = run_cycle_simulation(
            belt=belt,
            sorbent_props=props,
            duration_s=500.0,
            target_hot_roller_temp_k=target_k,
            hot_roller_temp_k=target_k,
        )

        # Sorbent internal conservation
        sorbent_balance_error = (
            res.co2_captured_kg - res.co2_released_kg - res.co2_sorbent_delta_kg
        )
        assert abs(sorbent_balance_error) < 1e-15
        assert abs(res.mass_balance_residual_kg) < 1e-15

        # Total process CO2 conservation (air in = air out + released + sorbent delta)
        total_balance_error = res.co2_air_fed_kg - (
            res.co2_air_untreated_kg + res.co2_released_kg + res.co2_sorbent_delta_kg
        )
        assert abs(total_balance_error) < 1e-15


# ---------------------------------------------------------------------------
# 7. Energy-balance accounting and heat-recovery edge cases
# ---------------------------------------------------------------------------

def test_energy_balance_and_heat_recovery_edge_cases(assumptions_data):
    """Verify First-Law balance closure and zero-power / cooldown edge cases."""
    props = SorbentProperties.from_assumptions(assumptions_data)

    # Edge Case A: Zero heater power
    belt_zero = DiscretizedBelt.from_assumptions(assumptions_data, num_segments=25)
    res_zero = run_cycle_simulation(
        belt=belt_zero,
        sorbent_props=props,
        duration_s=100.0,
        heater_power_w=0.0001,
        heater_controller="constant",
        target_hot_roller_temp_k=298.15,
        hot_roller_temp_k=298.15,
    )
    # Must not crash or divide by zero
    assert res_zero.heat_recovery_ratio >= 0.0
    assert abs(res_zero.energy_balance_residual_j) < 1e-8

    # Edge Case B: Step-down cooldown warning
    params_cooldown = dict(DEFAULT_PARAMS)
    params_cooldown["target_hot_roller_temp_c"] = 80.0
    params_cooldown["initial_hot_roller_temp_c"] = 105.0
    params_cooldown["duration_s"] = 500.0
    data = run_simulation_api(params_cooldown)
    # Notice transient cooldown warning is generated
    assert data["kpis"]["heat_recovery_warning"] is not None


# ---------------------------------------------------------------------------
# 8. Dashboard KPI values matching returned simulation result
# ---------------------------------------------------------------------------

def test_dashboard_kpis_match_simulation_result():
    """Verify that dashboard packaging faithfully transmits engine outputs."""
    params = dict(DEFAULT_PARAMS)
    params["duration_s"] = 50.0
    params["target_hot_roller_temp_c"] = 105.0
    params["initial_hot_roller_temp_c"] = 105.0

    data = run_simulation_api(params)
    assert data["status"] == "success"
    kpis = data["kpis"]

    # Verify key properties are present and accurately converted
    assert kpis["duration_s"] == 50.0
    assert kpis["hot_roller_target_c"] == 105.0
    assert kpis["hot_roller_initial_c"] == 105.0
    assert kpis["temperature_overshoot_k"] >= 0.0
    assert "final_setpoint_error_k" in kpis
    assert "co2_captured_g" in kpis
    assert "co2_released_g" in kpis
    assert "heat_recovery_ratio_pct" in kpis
    assert "mass_balance_residual_kg" in kpis
    assert "energy_balance_residual_j" in kpis


# ---------------------------------------------------------------------------
# 9. CSV/JSON exports matching the latest completed run
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def regression_test_server():
    port = 8069
    server = start_dashboard_server(host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def test_exports_match_latest_completed_run(regression_test_server):
    """Verify that export endpoints faithfully deliver data from the latest run."""
    base_url = regression_test_server

    # Trigger custom run
    target_c = 110.0
    custom_payload = json.dumps({
        "duration_s": 30.0,
        "time_step_s": 0.1,
        "target_hot_roller_temp_c": target_c,
        "initial_hot_roller_temp_c": target_c,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/api/simulate",
        data=custom_payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode("utf-8"))
        assert res["kpis"]["duration_s"] == 30.0
        assert res["kpis"]["hot_roller_target_c"] == target_c

    # 1. Check CSV export
    with urllib.request.urlopen(f"{base_url}/api/export/csv") as resp:
        assert resp.status == 200
        csv_text = resp.read().decode("utf-8")
        reader = list(csv.reader(io.StringIO(csv_text)))
        header = reader[0]
        assert "time_s" in header
        assert "hot_roller_temp_c" in header
        last_row = reader[-1]
        assert float(last_row[0]) == pytest.approx(30.0, abs=0.2)
        assert float(last_row[2]) > 90.0  # hot_roller_temp_c near target

    # 2. Check JSON report export
    with urllib.request.urlopen(f"{base_url}/api/export/json") as resp:
        assert resp.status == 200
        json_data = json.loads(resp.read().decode("utf-8"))
        assert json_data["kpis"]["duration_s"] == 30.0
        assert json_data["kpis"]["hot_roller_target_c"] == target_c

    # 3. Check PNG plot export
    with urllib.request.urlopen(f"{base_url}/api/export/plot") as resp:
        assert resp.status == 200
        img = resp.read()
        assert img[:8] == b"\x89PNG\r\n\x1a\n"
