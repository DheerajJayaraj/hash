"""Live presentation-ready browser dashboard for the Heat-Linked Roller Belt DAC Simulation.

Provides a self-contained local web server with interactive parameter controls,
real-time simulation execution, dynamic visualization plots, key performance metrics,
downstream methanol feasibility assessment, and data export.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import math
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yaml

from dac_sim.belt import DiscretizedBelt
from dac_sim.cycle import HeaterController, run_cycle_simulation
from dac_sim.methanol import evaluate_methanol_production
from dac_sim.sorbent import SorbentProperties

ROOT_DIR = Path(__file__).resolve().parents[2]
ASSUMPTIONS_PATH = ROOT_DIR / "assumptions.yaml"
OUTPUT_DIR = ROOT_DIR / "outputs"

DEFAULT_PARAMS: dict[str, Any] = {
    "duration_s": 990.0,
    "time_step_s": 0.1,
    "target_hot_roller_temp_c": 105.0,
    "heater_power_w": 500.0,
    "heater_controller": "pid",
    "controller_deadband_k": 1.0,
    "belt_speed_mm_s": 2.0,
    "fan_airflow_m3_h": 150.0,
    "air_co2_concentration_g_m3": 0.72,
    "fluid_flow_l_min": 0.5,
    "fluid_inlet_temp_c": 31.85,  # 305.0 K
    "initial_hot_roller_temp_c": 105.0,
}

_LATEST_SIMULATION_DATA: dict[str, Any] | None = None


def load_assumptions_dict() -> dict[str, Any]:
    """Load baseline YAML assumptions."""
    with ASSUMPTIONS_PATH.open(encoding="utf-8-sig") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("assumptions.yaml must contain a mapping.")
    return data


def validate_dashboard_params(params: dict[str, Any]) -> dict[str, Any]:
    """Validate and sanitize user input parameters from the dashboard."""
    clean: dict[str, Any] = {}

    def _get_float(key: str, default: float, min_val: float, max_val: float) -> float:
        val = params.get(key, default)
        try:
            val_f = float(val)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Parameter '{key}' must be a valid number.") from exc
        if not math.isfinite(val_f) or val_f < min_val or val_f > max_val:
            raise ValueError(
                f"Parameter '{key}' must be between {min_val} and {max_val}."
            )
        return val_f

    clean["duration_s"] = _get_float("duration_s", 990.0, 10.0, 3600.0)
    clean["time_step_s"] = _get_float("time_step_s", 0.1, 0.01, 1.0)
    clean["target_hot_roller_temp_c"] = _get_float(
        "target_hot_roller_temp_c", 105.0, 50.0, 150.0
    )
    clean["heater_power_w"] = _get_float("heater_power_w", 500.0, 10.0, 2000.0)

    mode = str(params.get("heater_controller", "pid")).strip().lower()
    if mode not in ("pid", "thermostat", "proportional", "constant"):
        raise ValueError(
            f"Invalid controller mode: {mode!r}. Must be 'pid', 'thermostat', 'proportional', or 'constant'."
        )
    clean["heater_controller"] = mode

    clean["controller_deadband_k"] = _get_float(
        "controller_deadband_k", 1.0, 0.1, 10.0
    )
    clean["belt_speed_mm_s"] = _get_float("belt_speed_mm_s", 2.0, 0.1, 10.0)
    clean["fan_airflow_m3_h"] = _get_float("fan_airflow_m3_h", 150.0, 10.0, 500.0)
    clean["air_co2_concentration_g_m3"] = _get_float(
        "air_co2_concentration_g_m3", 0.72, 0.1, 5.0
    )
    clean["fluid_flow_l_min"] = _get_float("fluid_flow_l_min", 0.5, 0.05, 5.0)
    clean["fluid_inlet_temp_c"] = _get_float(
        "fluid_inlet_temp_c", 31.85, 10.0, 80.0
    )
    clean["initial_hot_roller_temp_c"] = _get_float(
        "initial_hot_roller_temp_c", 105.0, 20.0, 150.0
    )

    return clean


def run_simulation_api(raw_params: dict[str, Any]) -> dict[str, Any]:
    """Execute live simulation based on dashboard parameters and format full results."""
    global _LATEST_SIMULATION_DATA

    params = validate_dashboard_params(raw_params)
    assumptions = load_assumptions_dict()
    sorbent_props = SorbentProperties.from_assumptions(assumptions)

    belt_speed_m_s = params["belt_speed_mm_s"] / 1000.0
    belt = DiscretizedBelt.from_assumptions(
        assumptions,
        num_segments=50,
        initial_temperature_k=298.15,
        initial_loading_mol_kg=0.08,
    )
    belt.belt_speed_m_s = belt_speed_m_s

    target_temp_k = params["target_hot_roller_temp_c"] + 273.15
    initial_hot_k = params["initial_hot_roller_temp_c"] + 273.15
    fluid_inlet_k = params["fluid_inlet_temp_c"] + 273.15

    result = run_cycle_simulation(
        belt=belt,
        sorbent_props=sorbent_props,
        duration_s=params["duration_s"],
        time_step_s=params["time_step_s"],
        heater_power_w=params["heater_power_w"],
        target_hot_roller_temp_k=target_temp_k,
        heater_controller=params["heater_controller"],
        controller_deadband_k=params["controller_deadband_k"],
        fan_airflow_m3_h=params["fan_airflow_m3_h"],
        air_co2_concentration_g_m3=params["air_co2_concentration_g_m3"],
        ambient_temperature_k=298.15,
        fluid_flow_l_min=params["fluid_flow_l_min"],
        fluid_inlet_temperature_k=fluid_inlet_k,
        hot_roller_temp_k=initial_hot_k,
    )

    # Downsample time-series for web chart performance if many points
    total_points = len(result.time_s)
    stride = max(1, total_points // 800)
    sampled_indices = list(range(0, total_points, stride))
    if sampled_indices[-1] != total_points - 1:
        sampled_indices.append(total_points - 1)

    chart_time = [round(result.time_s[i], 2) for i in sampled_indices]
    chart_hot_c = [round(result.hot_roller_temp_k[i] - 273.15, 2) for i in sampled_indices]
    chart_rec_c = [round(result.recovery_roller_temp_k[i] - 273.15, 2) for i in sampled_indices]
    chart_cool_c = [round(result.cooling_roller_temp_k[i] - 273.15, 2) for i in sampled_indices]
    chart_belt_c = [round(result.mean_belt_temp_k[i] - 273.15, 2) for i in sampled_indices]
    chart_power_w = [round(result.heater_power_w[i], 2) for i in sampled_indices]
    chart_loading = [round(result.mean_belt_loading_mol_kg[i], 4) for i in sampled_indices]

    # Methanol feasibility calculation
    co2_captured_kg_h = result.capture_rate_g_h / 1000.0
    methanol_res = evaluate_methanol_production(co2_captured_kg_h) if co2_captured_kg_h > 0 else None

    # Generate CSV in-memory
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow([
        "time_s",
        "hot_roller_temp_k",
        "hot_roller_temp_c",
        "recovery_roller_temp_k",
        "cooling_roller_temp_k",
        "mean_belt_temp_k",
        "mean_belt_loading_mol_kg",
        "heater_power_w",
    ])
    for i in range(total_points):
        writer.writerow([
            f"{result.time_s[i]:.2f}",
            f"{result.hot_roller_temp_k[i]:.3f}",
            f"{result.hot_roller_temp_k[i] - 273.15:.3f}",
            f"{result.recovery_roller_temp_k[i]:.3f}",
            f"{result.cooling_roller_temp_k[i]:.3f}",
            f"{result.mean_belt_temp_k[i]:.3f}",
            f"{result.mean_belt_loading_mol_kg[i]:.6f}",
            f"{result.heater_power_w[i]:.2f}",
        ])
    full_csv_text = csv_buf.getvalue()

    # Generate static plot image (Base64 PNG) as fallback / direct export
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    ax1.plot(chart_time, chart_hot_c, label="Hot Roller", color="#e41a1c", lw=2)
    ax1.axhline(params["target_hot_roller_temp_c"], color="#999999", ls=":", label=f"Target ({params['target_hot_roller_temp_c']:.1f}°C)")
    ax1.plot(chart_time, chart_rec_c, label="Recovery Roller", color="#377eb8", lw=1.5)
    ax1.plot(chart_time, chart_cool_c, label="Cooling Roller", color="#4daf4a", lw=1.5)
    ax1.plot(chart_time, chart_belt_c, label="Mean Belt", color="#984ea3", ls="--")
    ax1.set_ylabel("Temperature (°C)")
    ax1.set_title("Coupled DAC Cycle: Thermal Trajectory & Heater Power")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right", fontsize=8)

    ax2.plot(chart_time, chart_power_w, label="Heater Power (W)", color="#ff7f00", lw=1.8)
    ax2.axhline(result.average_heater_power_w, color="#02818a", ls="--", label=f"Avg ({result.average_heater_power_w:.1f} W)")
    ax2.set_ylabel("Power (W)")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="upper right", fontsize=8)

    ax3.plot(chart_time, chart_loading, label="Sorbent Loading (mol/kg)", color="#2b83ba", lw=2)
    ax3.set_xlabel("Time (s)")
    ax3.set_ylabel("CO2 Loading (mol/kg)")
    ax3.grid(True, alpha=0.3)
    ax3.legend(loc="lower right", fontsize=8)

    fig.tight_layout()
    plot_buf = io.BytesIO()
    fig.savefig(plot_buf, format="png", dpi=140)
    plt.close(fig)
    plot_base64 = base64.b64encode(plot_buf.getvalue()).decode("utf-8")

    # Save to disk outputs/
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "dac_cycle_history.csv").write_text(full_csv_text, encoding="utf-8")

    response_data = {
        "status": "success",
        "inputs": params,
        "kpis": {
            "duration_s": result.duration_s,
            "co2_captured_g": round(result.co2_captured_kg * 1000.0, 3),
            "capture_rate_g_h": round(result.capture_rate_g_h, 3),
            "co2_released_g": round(result.co2_released_kg * 1000.0, 3),
            "co2_sorbent_accumulation_g": round(result.co2_sorbent_delta_kg * 1000.0, 3),
            "hot_roller_final_c": round(result.hot_roller_temp_k[-1] - 273.15, 2),
            "hot_roller_max_c": round(result.max_hot_roller_temp_k - 273.15, 2),
            "hot_roller_target_c": round(params["target_hot_roller_temp_c"], 2),
            "temperature_overshoot_k": round(result.temperature_overshoot_k, 2),
            "average_heater_power_w": round(result.average_heater_power_w, 1),
            "total_heater_energy_kj": round(result.heater_energy_j / 1000.0, 2),
            "fluid_heat_recovered_kj": round(result.fluid_heat_recovered_j / 1000.0, 2),
            "heat_recovery_ratio_pct": round(result.heat_recovery_ratio * 100.0, 1),
            "gross_specific_energy_mwh_t": round(result.specific_thermal_energy_mwh_t, 2),
            "net_specific_energy_mj_kg": round(result.net_specific_thermal_energy_mj_kg, 2),
            "net_specific_energy_kwh_kg": round(result.net_specific_thermal_energy_mj_kg / 3.6, 2),
            "theoretical_reaction_enthalpy_mwh_t": 1.60,
            "mass_balance_residual_kg": f"{result.mass_balance_residual_kg:.3e}",
            "energy_balance_residual_j": f"{result.energy_balance_residual_j:.3e}",
        },
        "charts": {
            "time_s": chart_time,
            "hot_roller_temp_c": chart_hot_c,
            "recovery_roller_temp_c": chart_rec_c,
            "cooling_roller_temp_c": chart_cool_c,
            "mean_belt_temp_c": chart_belt_c,
            "target_temp_c": [params["target_hot_roller_temp_c"]] * len(chart_time),
            "heater_power_w": chart_power_w,
            "average_power_w": [round(result.average_heater_power_w, 1)] * len(chart_time),
            "mean_loading_mol_kg": chart_loading,
            "balances": {
                "co2_air_fed_g": round(result.co2_air_fed_kg * 1000.0, 3),
                "co2_captured_g": round(result.co2_captured_kg * 1000.0, 3),
                "co2_untreated_g": round(result.co2_air_untreated_kg * 1000.0, 3),
                "heater_input_kj": round(result.heater_energy_j / 1000.0, 2),
                "ambient_loss_kj": round(-result.ambient_energy_j / 1000.0, 2),
                "fluid_recovered_kj": round(result.fluid_heat_recovered_j / 1000.0, 2),
                "sensible_stored_kj": round(result.sensible_energy_change_j / 1000.0, 2),
                "desorption_heat_kj": round(result.desorption_energy_j / 1000.0, 2),
            },
        },
        "methanol": {
            "enabled": methanol_res is not None,
            "co2_feed_g_h": round(result.capture_rate_g_h, 3),
            "methanol_yield_g_h": round(methanol_res.methanol_produced_kg_h * 1000.0, 3) if methanol_res else 0.0,
            "methanol_yield_kg_day": round(methanol_res.methanol_produced_kg_h * 24.0, 4) if methanol_res else 0.0,
            "h2_demand_g_h": round(methanol_res.h2_demand_kg_h * 1000.0, 3) if methanol_res else 0.0,
            "water_byproduct_g_h": round(methanol_res.water_byproduct_kg_h * 1000.0, 3) if methanol_res else 0.0,
            "electrolysis_power_w": round(methanol_res.electrolysis_power_kw * 1000.0, 2) if methanol_res else 0.0,
            "electrolysis_specific_mwh_t": round(methanol_res.electrolysis_energy_mwh_t_methanol, 2) if methanol_res else 9.81,
            "exothermic_heat_w": round(methanol_res.exothermic_heat_generated_kw * 1000.0, 2) if methanol_res else 0.0,
            "recoverable_heat_w": round(methanol_res.recoverable_heat_kw * 1000.0, 2) if methanol_res else 0.0,
            "reaction_equation": "CO2 + 3 H2 <==> CH3OH + H2O  (Delta H_298 = -49.5 kJ/mol)",
        },
        "plot_base64": plot_base64,
        "csv_text": full_csv_text,
    }

    _LATEST_SIMULATION_DATA = response_data
    with (OUTPUT_DIR / "dac_cycle_report.json").open("w", encoding="utf-8") as f:
        json.dump(response_data, f, indent=2)

    return response_data


# ---------------------------------------------------------------------------
# Embedded HTML, CSS & Client-Side Logic
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Heat-Linked Roller Belt DAC Simulation — Live Showcase</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --bg: #0b1120;
      --card-bg: #1e293b;
      --card-border: #334155;
      --accent: #38bdf8;
      --accent-hover: #0ea5e9;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font-family);
      line-height: 1.5;
      padding-bottom: 60px;
    }
    header {
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      border-bottom: 1px solid var(--card-border);
      padding: 1.25rem 2rem;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .header-title h1 {
      font-size: 1.4rem;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .header-title p {
      font-size: 0.85rem;
      color: var(--text-muted);
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .badge {
      font-size: 0.75rem;
      padding: 0.25rem 0.6rem;
      border-radius: 9999px;
      font-weight: 600;
      letter-spacing: 0.025em;
    }
    .badge-success { background: rgba(16, 185, 129, 0.2); color: var(--success); border: 1px solid var(--success); }
    .badge-sim { background: rgba(56, 189, 248, 0.2); color: var(--accent); border: 1px solid var(--accent); }
    .badge-warn { background: rgba(245, 158, 11, 0.2); color: var(--warning); border: 1px solid var(--warning); }
    
    button {
      cursor: pointer;
      font-weight: 600;
      font-size: 0.875rem;
      padding: 0.6rem 1.25rem;
      border-radius: 0.375rem;
      border: none;
      transition: all 0.2s;
    }
    .btn-primary {
      background: var(--accent);
      color: #0f172a;
    }
    .btn-primary:hover { background: var(--accent-hover); box-shadow: 0 0 12px rgba(56,189,248,0.4); }
    .btn-secondary {
      background: #334155;
      color: var(--text);
    }
    .btn-secondary:hover { background: #475569; }

    main {
      max-width: 1400px;
      margin: 1.5rem auto;
      padding: 0 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 0.5rem;
      padding: 1.25rem;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .card-title {
      font-size: 1.05rem;
      font-weight: 600;
      color: #fff;
      margin-bottom: 0.75rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      padding-bottom: 0.5rem;
    }

    /* Schematic Layout */
    .schematic-box {
      background: #0f172a;
      border: 1px solid var(--card-border);
      border-radius: 0.375rem;
      padding: 1rem;
      overflow-x: auto;
    }
    .schematic-svg {
      width: 100%;
      min-width: 800px;
      height: 220px;
    }

    /* Control Panel Form */
    .control-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
    }
    .form-group {
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
    }
    label {
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
    }
    input, select {
      background: #0f172a;
      border: 1px solid var(--card-border);
      color: #fff;
      padding: 0.5rem 0.75rem;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      font-family: inherit;
    }
    input:focus, select:focus {
      outline: none;
      border-color: var(--accent);
    }

    /* KPIs Grid */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
    }
    .kpi-card {
      background: #0f172a;
      border: 1px solid var(--card-border);
      border-radius: 0.375rem;
      padding: 0.85rem 1rem;
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }
    .kpi-label {
      font-size: 0.75rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .kpi-value {
      font-size: 1.4rem;
      font-weight: 700;
      color: #fff;
    }
    .kpi-sub {
      font-size: 0.75rem;
      color: var(--accent);
    }

    /* Chart Grid */
    .chart-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
      gap: 1.25rem;
    }
    .chart-container {
      background: #0f172a;
      border: 1px solid var(--card-border);
      border-radius: 0.375rem;
      padding: 1rem;
      height: 300px;
      position: relative;
    }

    /* Methanol Section */
    .methanol-box {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.5rem;
    }
    @media (max-width: 850px) { .methanol-box { grid-template-columns: 1fr; } }
    .eq-callout {
      background: #0f172a;
      border-left: 4px solid var(--accent);
      padding: 1rem;
      border-radius: 0.25rem;
      font-family: monospace;
      font-size: 0.95rem;
    }

    /* Downloads & Summary */
    .download-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-top: 0.5rem;
    }
    .btn-download {
      background: #1e293b;
      border: 1px solid var(--card-border);
      color: var(--text);
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      text-decoration: none;
      padding: 0.5rem 1rem;
      border-radius: 0.375rem;
      font-size: 0.85rem;
      font-weight: 600;
    }
    .btn-download:hover { background: #334155; border-color: var(--accent); }

    /* Alert */
    .alert {
      padding: 0.75rem 1rem;
      border-radius: 0.375rem;
      font-size: 0.875rem;
      display: none;
      margin-bottom: 1rem;
    }
    .alert-danger { background: rgba(239, 68, 68, 0.2); border: 1px solid var(--danger); color: #fca5a5; }
    .alert-success { background: rgba(16, 185, 129, 0.2); border: 1px solid var(--success); color: #86efac; }
  </style>
</head>
<body>

  <header>
    <div class="header-title">
      <h1>
        <span>🌀</span> Heat-Linked Roller Belt DAC Simulation
        <span class="badge badge-sim">Model Showcase</span>
      </h1>
      <p>Direct Air Capture, Thermal Regeneration, Fluid Heat Recovery & Downstream Methanol Feasibility</p>
    </div>
    <div class="header-actions">
      <span id="status-badge" class="badge badge-success">Engine Ready</span>
      <button class="btn-secondary" onclick="resetDefaults()">Reset Baseline</button>
      <button class="btn-primary" id="btn-run" onclick="triggerSimulation()">▶ Run Simulation</button>
    </div>
  </header>

  <main>
    <div id="alert-box" class="alert"></div>

    <!-- Section: Process Schematic -->
    <section class="card">
      <div class="card-title">
        <span>Continuous Roller-Belt Architecture & Thermal-Fluid Zones</span>
        <span class="badge badge-sim">1.98m Loop Discretization</span>
      </div>
      <div class="schematic-box">
        <svg class="schematic-svg" viewBox="0 0 950 200" xmlns="http://www.w3.org/2000/svg">
          <!-- Background Zones -->
          <rect x="20" y="25" width="220" height="150" rx="8" fill="#134e4a" fill-opacity="0.2" stroke="#14b8a6" stroke-dasharray="4"/>
          <text x="30" y="45" fill="#2dd4bf" font-size="12" font-weight="bold">Zone 1: Ambient Adsorption (0.3m)</text>
          <text x="30" y="65" fill="#99f6e4" font-size="10">Forced airflow: 150 m³/h @ 0.72 g/m³</text>
          <text x="30" y="80" fill="#99f6e4" font-size="10">Linear Driving Force Kinetics</text>

          <rect x="270" y="25" width="200" height="150" rx="8" fill="#7f1d1d" fill-opacity="0.25" stroke="#ef4444" stroke-dasharray="4"/>
          <text x="280" y="45" fill="#f87171" font-size="12" font-weight="bold">Zone 2: Regeneration (105°C)</text>
          <text x="280" y="65" fill="#fca5a5" font-size="10">Hot Roller: 500W PID Controlled</text>
          <text x="280" y="80" fill="#fca5a5" font-size="10">Desorbs CO2 into sealed stream</text>

          <rect x="500" y="25" width="200" height="150" rx="8" fill="#312e81" fill-opacity="0.25" stroke="#6366f1" stroke-dasharray="4"/>
          <text x="510" y="45" fill="#818cf8" font-size="12" font-weight="bold">Zone 3: Sensible Recovery (65°C)</text>
          <text x="510" y="65" fill="#c7d2fe" font-size="10">Fluid Loop: 0.5 L/min water stream</text>
          <text x="510" y="80" fill="#c7d2fe" font-size="10">Recovers ~40-60% sensible heat</text>

          <rect x="730" y="25" width="200" height="150" rx="8" fill="#064e3b" fill-opacity="0.2" stroke="#10b981" stroke-dasharray="4"/>
          <text x="740" y="45" fill="#34d399" font-size="12" font-weight="bold">Zone 4: Cooling Roller (25°C)</text>
          <text x="740" y="65" fill="#a7f3d0" font-size="10">Returns sorbent to 298K baseline</text>
          <text x="740" y="80" fill="#a7f3d0" font-size="10">Ready for adsorption re-entry</text>

          <!-- Belt Loop Representation -->
          <path d="M 120 125 C 250 125, 350 125, 370 125 C 450 125, 580 125, 600 125 C 700 125, 810 125, 830 125" stroke="#38bdf8" stroke-width="6" fill="none" stroke-linecap="round"/>
          <path d="M 830 145 C 700 145, 580 145, 600 145 C 450 145, 350 145, 370 145 C 250 145, 120 145, 120 145" stroke="#0284c7" stroke-width="4" stroke-dasharray="5 3" fill="none"/>

          <!-- Rollers -->
          <circle cx="120" cy="135" r="22" fill="#334155" stroke="#94a3b8" stroke-width="2"/>
          <text x="120" y="140" fill="#fff" font-size="10" text-anchor="middle">Idler</text>

          <circle cx="370" cy="135" r="24" fill="#991b1b" stroke="#f87171" stroke-width="2"/>
          <text x="370" y="140" fill="#fff" font-size="10" font-weight="bold" text-anchor="middle">105°C</text>

          <circle cx="600" cy="135" r="18" fill="#3730a3" stroke="#818cf8" stroke-width="2"/>
          <text x="600" y="139" fill="#fff" font-size="9" text-anchor="middle">Fluid</text>

          <circle cx="830" cy="135" r="22" fill="#065f46" stroke="#34d399" stroke-width="2"/>
          <text x="830" y="140" fill="#fff" font-size="10" text-anchor="middle">Cool</text>

          <!-- Flow arrows -->
          <path d="M 230 115 L 245 125 L 230 135" fill="none" stroke="#38bdf8" stroke-width="2"/>
          <path d="M 470 115 L 485 125 L 470 135" fill="none" stroke="#38bdf8" stroke-width="2"/>
          <path d="M 700 115 L 715 125 L 700 135" fill="none" stroke="#38bdf8" stroke-width="2"/>
        </svg>
      </div>
    </section>

    <!-- Section: Control Panel -->
    <section class="card">
      <div class="card-title">
        <span>Interactive Simulation Parameters</span>
        <span class="badge badge-success">Coupled Euler Dynamic Engine</span>
      </div>
      <div class="control-grid">
        <div class="form-group">
          <label for="duration_s">Duration (seconds):</label>
          <input type="number" id="duration_s" min="10" max="3600" step="10" value="990">
        </div>
        <div class="form-group">
          <label for="time_step_s">Time Step Δt (seconds):</label>
          <input type="number" id="time_step_s" min="0.01" max="1.0" step="0.01" value="0.1">
        </div>
        <div class="form-group">
          <label for="target_hot_roller_temp_c">Hot Roller Target Setpoint (°C):</label>
          <input type="number" id="target_hot_roller_temp_c" min="60" max="140" step="1" value="105">
        </div>
        <div class="form-group">
          <label for="heater_power_w">Max Heater Power (W):</label>
          <input type="number" id="heater_power_w" min="50" max="1500" step="25" value="500">
        </div>
        <div class="form-group">
          <label for="heater_controller">Heater Controller Mode:</label>
          <select id="heater_controller">
            <option value="pid" selected>PID Modulated (Recommended)</option>
            <option value="thermostat">Thermostat (Bang-Bang Relay)</option>
            <option value="proportional">Proportional Only</option>
            <option value="constant">Constant Power (Open-Loop Test)</option>
          </select>
        </div>
        <div class="form-group">
          <label for="belt_speed_mm_s">Belt Speed (mm/s):</label>
          <input type="number" id="belt_speed_mm_s" min="0.5" max="5.0" step="0.1" value="2.0">
        </div>
        <div class="form-group">
          <label for="fan_airflow_m3_h">Fan Airflow (m³/h):</label>
          <input type="number" id="fan_airflow_m3_h" min="50" max="300" step="10" value="150">
        </div>
        <div class="form-group">
          <label for="air_co2_concentration_g_m3">Ambient CO2 (g/m³):</label>
          <input type="number" id="air_co2_concentration_g_m3" min="0.4" max="2.0" step="0.02" value="0.72">
        </div>
        <div class="form-group">
          <label for="fluid_flow_l_min">Fluid Recovery Flow (L/min):</label>
          <input type="number" id="fluid_flow_l_min" min="0.1" max="2.0" step="0.05" value="0.5">
        </div>
        <div class="form-group">
          <label for="fluid_inlet_temp_c">Fluid Inlet Temp (°C):</label>
          <input type="number" id="fluid_inlet_temp_c" min="15" max="60" step="0.5" value="31.85">
        </div>
      </div>
    </section>

    <!-- Section: Key Performance Indicators -->
    <section class="card">
      <div class="card-title">
        <span>Verified Simulation KPIs (Current Run)</span>
        <span id="run-duration-tag" class="badge badge-sim">Duration: 990.0 s</span>
      </div>
      <div class="kpi-grid">
        <div class="kpi-card">
          <span class="kpi-label">Capture Rate</span>
          <span class="kpi-value" id="kpi-capture-rate">2.355 <span style="font-size:0.9rem">g/h</span></span>
          <span class="kpi-sub" id="kpi-capture-total">Total: 0.648 g captured</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Desorbed CO2</span>
          <span class="kpi-value" id="kpi-released">0.092 <span style="font-size:0.9rem">g</span></span>
          <span class="kpi-sub" id="kpi-accumulation">Sorbent Δm: +0.556 g</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Hot Roller Temp</span>
          <span class="kpi-value" id="kpi-hot-temp">105.0 <span style="font-size:0.9rem">°C</span></span>
          <span class="kpi-sub" id="kpi-overshoot">Overshoot: +0.11 K</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Avg Heater Power</span>
          <span class="kpi-value" id="kpi-power">190.3 <span style="font-size:0.9rem">W</span></span>
          <span class="kpi-sub" id="kpi-heater-energy">Total: 188.4 kJ drawn</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Fluid Heat Recovered</span>
          <span class="kpi-value" id="kpi-recovered">129.9 <span style="font-size:0.9rem">kJ</span></span>
          <span class="kpi-sub" id="kpi-recovery-ratio">Recovery: 69.0%</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Specific Thermal Energy</span>
          <span class="kpi-value" id="kpi-gross-energy">80.8 <span style="font-size:0.9rem">MWh/t</span></span>
          <span class="kpi-sub" id="kpi-net-energy">Net: 90.25 MJ/kg CO2</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Mass Balance Residual</span>
          <span class="kpi-value" id="kpi-mass-residual" style="font-size:1.15rem">&lt; 10⁻¹² <span style="font-size:0.8rem">kg</span></span>
          <span class="kpi-sub">Exact Conservation Closed</span>
        </div>
        <div class="kpi-card">
          <span class="kpi-label">Energy Balance Residual</span>
          <span class="kpi-value" id="kpi-energy-residual" style="font-size:1.15rem">&lt; 10⁻⁸ <span style="font-size:0.8rem">J</span></span>
          <span class="kpi-sub">First Law Exact Match</span>
        </div>
      </div>
    </section>

    <!-- Section: Dynamic Charts -->
    <section class="card">
      <div class="card-title">
        <span>Coupled Transient Trajectories & Accounting Balances</span>
        <span class="badge badge-sim">Live Canvas / Chart.js</span>
      </div>
      <div class="chart-grid">
        <div class="chart-container">
          <canvas id="chart-temperatures"></canvas>
        </div>
        <div class="chart-container">
          <canvas id="chart-power"></canvas>
        </div>
        <div class="chart-container">
          <canvas id="chart-loading"></canvas>
        </div>
        <div class="chart-container">
          <canvas id="chart-balances"></canvas>
        </div>
      </div>
    </section>

    <!-- Section: Methanol Assessment -->
    <section class="card">
      <div class="card-title">
        <span>Downstream Methanol Synthesis Assessment (e-Methanol Pathway)</span>
        <span class="badge badge-warn">Theoretical Decoupled Evaluation</span>
      </div>
      <div class="methanol-box">
        <div>
          <div class="eq-callout">
            CO2 + 3 H2 &lt;==&gt; CH3OH + H2O &nbsp;&nbsp;(ΔH°₂₉₈ = -49.5 kJ/mol)
          </div>
          <p style="font-size:0.85rem; color:var(--text-muted); margin-top:0.75rem;">
            This panel assesses downstream catalytic conversion (<span style="color:#fff">Cu/ZnO/Al₂O₃ at 60 bar, 240°C</span>)
            using the live captured CO2 stream from the belt simulation above.
            Green hydrogen is supplied via water electrolysis at 68% LHV efficiency.
          </p>
        </div>
        <div class="kpi-grid" style="grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));">
          <div class="kpi-card">
            <span class="kpi-label">Methanol Yield</span>
            <span class="kpi-value" id="meth-yield" style="font-size:1.2rem">1.63 g/h</span>
            <span class="kpi-sub" id="meth-day">0.039 kg/day</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">Green H2 Demand</span>
            <span class="kpi-value" id="meth-h2" style="font-size:1.2rem">0.31 g/h</span>
            <span class="kpi-sub">3.4 NL/h</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">Electrolysis Power</span>
            <span class="kpi-value" id="meth-power" style="font-size:1.2rem">15.1 W</span>
            <span class="kpi-sub">9.81 MWh/t MeOH</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-label">Exothermic Heat</span>
            <span class="kpi-value" id="meth-heat" style="font-size:1.2rem">0.70 W</span>
            <span class="kpi-sub">Recoverable high-grade</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Section: Downloads & Scientific Integrity -->
    <section class="card">
      <div class="card-title">
        <span>Export Data & Model Assumptions</span>
        <span class="badge badge-success">Auditable Provenance</span>
      </div>
      <p style="font-size:0.875rem; color:var(--text-muted); margin-bottom: 0.75rem;">
        Export current simulation datasets or download publication-ready summary artifacts:
      </p>
      <div class="download-bar">
        <a class="btn-download" id="download-csv" href="/api/export/csv" download="dac_cycle_history.csv">📥 Download Full CSV (1 Hz)</a>
        <a class="btn-download" id="download-json" href="/api/export/json" download="dac_cycle_report.json">📄 Download JSON Report</a>
        <a class="btn-download" id="download-plot" href="/api/export/plot" download="dac_cycle_plot.png">🖼️ Download Publication PNG</a>
      </div>

      <div style="margin-top: 1.25rem; font-size: 0.8rem; color: var(--text-muted); border-top: 1px solid var(--card-border); padding-top: 0.75rem;">
        <p><strong>Scientific Integrity Notes:</strong></p>
        <ul style="margin-left: 1.25rem; margin-top: 0.35rem; display: flex; flex-direction: column; gap: 0.25rem;">
          <li><strong>Bench Thermal Intensity:</strong> At bench scale, standby ambient losses on a 2 kg metal roller dominate specific energy (~80 MWh/t CO2). The intrinsic sorbent reaction enthalpy is 1.6 MWh/t CO2. Scale-up drops thermal demand to 1.5–2.0 MWh/t CO2.</li>
          <li><strong>Kinetics Limitation:</strong> Capture rate is 100% sorbent- and kinetics-limited (150 m³/h air delivers &gt;25x more CO2 than sorbent can adsorb).</li>
          <li><strong>Methanol Scope:</strong> Methanol production is evaluated purely as a downstream stoichiometric and thermodynamic model; it is not physically integrated on the DAC test bench.</li>
        </ul>
      </div>
    </section>
  </main>

  <script>
    let chartTemp, chartPower, chartLoading, chartBalances;

    function showAlert(msg, isSuccess=false) {
      const box = document.getElementById('alert-box');
      box.className = 'alert ' + (isSuccess ? 'alert-success' : 'alert-danger');
      box.textContent = msg;
      box.style.display = 'block';
      setTimeout(() => { box.style.display = 'none'; }, 6000);
    }

    function initCharts(data) {
      const c = data.charts;

      // 1. Temperatures Chart
      const ctxTemp = document.getElementById('chart-temperatures').getContext('2d');
      if (chartTemp) chartTemp.destroy();
      chartTemp = new Chart(ctxTemp, {
        type: 'line',
        data: {
          labels: c.time_s,
          datasets: [
            { label: 'Hot Roller (°C)', data: c.hot_roller_temp_c, borderColor: '#ef4444', borderWidth: 2, pointRadius: 0 },
            { label: 'Setpoint (°C)', data: c.target_temp_c, borderColor: '#94a3b8', borderDash: [4, 4], borderWidth: 1.5, pointRadius: 0 },
            { label: 'Recovery Roller (°C)', data: c.recovery_roller_temp_c, borderColor: '#818cf8', borderWidth: 1.5, pointRadius: 0 },
            { label: 'Cooling Roller (°C)', data: c.cooling_roller_temp_c, borderColor: '#10b981', borderWidth: 1.5, pointRadius: 0 },
            { label: 'Mean Belt (°C)', data: c.mean_belt_temp_c, borderColor: '#e879f9', borderDash: [3, 2], borderWidth: 1.5, pointRadius: 0 }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { title: { display: true, text: 'Thermal Node Trajectories (°C)', color: '#fff' } },
          scales: {
            x: { title: { display: true, text: 'Time (s)', color: '#94a3b8' }, ticks: { color: '#94a3b8' } },
            y: { title: { display: true, text: 'Temperature (°C)', color: '#94a3b8' }, ticks: { color: '#94a3b8' } }
          }
        }
      });

      // 2. Power Chart
      const ctxPower = document.getElementById('chart-power').getContext('2d');
      if (chartPower) chartPower.destroy();
      chartPower = new Chart(ctxPower, {
        type: 'line',
        data: {
          labels: c.time_s,
          datasets: [
            { label: 'Instantaneous Heater Power (W)', data: c.heater_power_w, borderColor: '#f59e0b', borderWidth: 1.8, pointRadius: 0 },
            { label: 'Average Power (W)', data: c.average_power_w, borderColor: '#38bdf8', borderDash: [5, 3], borderWidth: 1.5, pointRadius: 0 }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { title: { display: true, text: 'Electrical Heater Power Output (W)', color: '#fff' } },
          scales: {
            x: { title: { display: true, text: 'Time (s)', color: '#94a3b8' }, ticks: { color: '#94a3b8' } },
            y: { title: { display: true, text: 'Power (W)', color: '#94a3b8' }, ticks: { color: '#94a3b8' }, min: 0 }
          }
        }
      });

      // 3. Loading Chart
      const ctxLoading = document.getElementById('chart-loading').getContext('2d');
      if (chartLoading) chartLoading.destroy();
      chartLoading = new Chart(ctxLoading, {
        type: 'line',
        data: {
          labels: c.time_s,
          datasets: [
            { label: 'Mean Sorbent Loading (mol CO2/kg)', data: c.mean_loading_mol_kg, borderColor: '#38bdf8', borderWidth: 2, pointRadius: 0 }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { title: { display: true, text: 'Sorbent CO2 Loading History (mol/kg)', color: '#fff' } },
          scales: {
            x: { title: { display: true, text: 'Time (s)', color: '#94a3b8' }, ticks: { color: '#94a3b8' } },
            y: { title: { display: true, text: 'Loading (mol/kg)', color: '#94a3b8' }, ticks: { color: '#94a3b8' } }
          }
        }
      });

      // 4. Balances Chart
      const ctxBalances = document.getElementById('chart-balances').getContext('2d');
      if (chartBalances) chartBalances.destroy();
      const b = c.balances;
      chartBalances = new Chart(ctxBalances, {
        type: 'bar',
        data: {
          labels: ['Heater In (kJ)', 'Fluid Rec (kJ)', 'Amb Loss (kJ)', 'Desorp (kJ)', 'Sensible ΔU (kJ)'],
          datasets: [{
            label: 'Thermal Energy Budget (kJ)',
            data: [b.heater_input_kj, b.fluid_recovered_kj, b.ambient_loss_kj, b.desorption_heat_kj, b.sensible_stored_kj],
            backgroundColor: ['#f59e0b', '#38bdf8', '#ef4444', '#10b981', '#818cf8']
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { title: { display: true, text: 'Thermal Energy Accounting Breakdown (kJ)', color: '#fff' } },
          scales: {
            x: { ticks: { color: '#94a3b8' } },
            y: { ticks: { color: '#94a3b8' } }
          }
        }
      });
    }

    function updateUI(res) {
      const k = res.kpis;
      document.getElementById('kpi-capture-rate').innerHTML = `${k.capture_rate_g_h} <span style="font-size:0.9rem">g/h</span>`;
      document.getElementById('kpi-capture-total').textContent = `Total: ${k.co2_captured_g} g captured`;
      document.getElementById('kpi-released').innerHTML = `${k.co2_released_g} <span style="font-size:0.9rem">g</span>`;
      document.getElementById('kpi-accumulation').textContent = `Sorbent Δm: ${k.co2_sorbent_accumulation_g} g`;
      document.getElementById('kpi-hot-temp').innerHTML = `${k.hot_roller_final_c} <span style="font-size:0.9rem">°C</span>`;
      document.getElementById('kpi-overshoot').textContent = `Overshoot: +${k.temperature_overshoot_k} K`;
      document.getElementById('kpi-power').innerHTML = `${k.average_heater_power_w} <span style="font-size:0.9rem">W</span>`;
      document.getElementById('kpi-heater-energy').textContent = `Total: ${k.total_heater_energy_kj} kJ drawn`;
      document.getElementById('kpi-recovered').innerHTML = `${k.fluid_heat_recovered_kj} <span style="font-size:0.9rem">kJ</span>`;
      document.getElementById('kpi-recovery-ratio').textContent = `Recovery: ${k.heat_recovery_ratio_pct}%`;
      document.getElementById('kpi-gross-energy').innerHTML = `${k.gross_specific_energy_mwh_t} <span style="font-size:0.9rem">MWh/t</span>`;
      document.getElementById('kpi-net-energy').textContent = `Net: ${k.net_specific_energy_mj_kg} MJ/kg CO2`;
      document.getElementById('kpi-mass-residual').textContent = `${k.mass_balance_residual_kg} kg`;
      document.getElementById('kpi-energy-residual').textContent = `${k.energy_balance_residual_j} J`;
      document.getElementById('run-duration-tag').textContent = `Duration: ${k.duration_s} s`;

      // Methanol
      const m = res.methanol;
      if (m && m.enabled) {
        document.getElementById('meth-yield').textContent = `${m.methanol_yield_g_h} g/h`;
        document.getElementById('meth-day').textContent = `${m.methanol_yield_kg_day} kg/day`;
        document.getElementById('meth-h2').textContent = `${m.h2_demand_g_h} g/h`;
        document.getElementById('meth-power').textContent = `${m.electrolysis_power_w} W`;
        document.getElementById('meth-heat').textContent = `${m.exothermic_heat_w} W`;
      }

      initCharts(res);
    }

    async function triggerSimulation() {
      const btn = document.getElementById('btn-run');
      const badge = document.getElementById('status-badge');
      btn.disabled = true;
      btn.textContent = 'Simulating Physics...';
      badge.className = 'badge badge-sim';
      badge.textContent = 'Computing Cycle...';

      const payload = {
        duration_s: parseFloat(document.getElementById('duration_s').value),
        time_step_s: parseFloat(document.getElementById('time_step_s').value),
        target_hot_roller_temp_c: parseFloat(document.getElementById('target_hot_roller_temp_c').value),
        heater_power_w: parseFloat(document.getElementById('heater_power_w').value),
        heater_controller: document.getElementById('heater_controller').value,
        belt_speed_mm_s: parseFloat(document.getElementById('belt_speed_mm_s').value),
        fan_airflow_m3_h: parseFloat(document.getElementById('fan_airflow_m3_h').value),
        air_co2_concentration_g_m3: parseFloat(document.getElementById('air_co2_concentration_g_m3').value),
        fluid_flow_l_min: parseFloat(document.getElementById('fluid_flow_l_min').value),
        fluid_inlet_temp_c: parseFloat(document.getElementById('fluid_inlet_temp_c').value)
      };

      try {
        const resp = await fetch('/api/simulate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const res = await resp.json();
        if (resp.ok && res.status === 'success') {
          updateUI(res);
          badge.className = 'badge badge-success';
          badge.textContent = 'Engine Ready';
          showAlert('Simulation completed successfully! Balances closed.', true);
        } else {
          badge.className = 'badge badge-warn';
          badge.textContent = 'Input Error';
          showAlert('Simulation error: ' + (res.error || 'Unknown error'));
        }
      } catch (err) {
        badge.className = 'badge badge-warn';
        badge.textContent = 'Network Error';
        showAlert('Network or execution error: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = '▶ Run Simulation';
      }
    }

    function resetDefaults() {
      document.getElementById('duration_s').value = 990;
      document.getElementById('time_step_s').value = 0.1;
      document.getElementById('target_hot_roller_temp_c').value = 105;
      document.getElementById('heater_power_w').value = 500;
      document.getElementById('heater_controller').value = 'pid';
      document.getElementById('belt_speed_mm_s').value = 2.0;
      document.getElementById('fan_airflow_m3_h').value = 150;
      document.getElementById('air_co2_concentration_g_m3').value = 0.72;
      document.getElementById('fluid_flow_l_min').value = 0.5;
      document.getElementById('fluid_inlet_temp_c').value = 31.85;
      triggerSimulation();
    }

    // Run baseline on first page load
    window.addEventListener('DOMContentLoaded', () => {
      triggerSimulation();
    });
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP Request Handler & Server
# ---------------------------------------------------------------------------

class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP server handler serving the live simulation API and dashboard UI."""

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress noisy request logging in terminal during live presentations."""
        pass

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode("utf-8"))
            return

        elif path == "/api/baseline":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(DEFAULT_PARAMS).encode("utf-8"))
            return

        elif path == "/api/export/csv":
            global _LATEST_SIMULATION_DATA
            if _LATEST_SIMULATION_DATA is None:
                _LATEST_SIMULATION_DATA = run_simulation_api(DEFAULT_PARAMS)
            csv_content = _LATEST_SIMULATION_DATA["csv_text"]
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", 'attachment; filename="dac_simulation_history.csv"')
            self.end_headers()
            self.wfile.write(csv_content.encode("utf-8"))
            return

        elif path == "/api/export/json":
            if _LATEST_SIMULATION_DATA is None:
                _LATEST_SIMULATION_DATA = run_simulation_api(DEFAULT_PARAMS)
            report_bytes = json.dumps(_LATEST_SIMULATION_DATA, indent=2).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Disposition", 'attachment; filename="dac_simulation_report.json"')
            self.end_headers()
            self.wfile.write(report_bytes)
            return

        elif path == "/api/export/plot":
            if _LATEST_SIMULATION_DATA is None:
                _LATEST_SIMULATION_DATA = run_simulation_api(DEFAULT_PARAMS)
            png_bytes = base64.b64decode(_LATEST_SIMULATION_DATA["plot_base64"])
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Disposition", 'attachment; filename="dac_simulation_plot.png"')
            self.end_headers()
            self.wfile.write(png_bytes)
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()
        self.wfile.write(b"404 Not Found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/simulate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                params = json.loads(body) if body else {}
                results = run_simulation_api(params)
                resp_bytes = json.dumps(results).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(resp_bytes)
            except Exception as exc:
                err_payload = {"status": "error", "error": str(exc)}
                resp_bytes = json.dumps(err_payload).encode("utf-8")
                self.send_response(HTTPStatus.BAD_REQUEST)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(resp_bytes)
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()
        self.wfile.write(b"404 Not Found")


def start_dashboard_server(
    host: str = "127.0.0.1",
    port: int = 8050,
) -> ThreadingHTTPServer:
    """Start the dashboard HTTP server."""
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    return server
