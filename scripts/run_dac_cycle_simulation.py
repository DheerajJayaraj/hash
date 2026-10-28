"""Run and report a complete DAC cycle simulation with mass and energy balances."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yaml

from dac_sim.belt import DiscretizedBelt
from dac_sim.cycle import run_cycle_simulation
from dac_sim.sorbent import SorbentProperties

ROOT = Path(__file__).resolve().parents[1]
ASSUMPTIONS_PATH = ROOT / "assumptions.yaml"
OUTPUT_DIR = ROOT / "outputs"


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a YAML mapping.")
    return data


def export_cycle_csv(result, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "time_s",
            "hot_roller_temp_k",
            "recovery_roller_temp_k",
            "cooling_roller_temp_k",
            "mean_belt_temp_k",
            "mean_belt_loading_mol_kg",
            "heater_power_w",
        ])
        for i in range(len(result.time_s)):
            writer.writerow([
                f"{result.time_s[i]:.2f}",
                f"{result.hot_roller_temp_k[i]:.3f}",
                f"{result.recovery_roller_temp_k[i]:.3f}",
                f"{result.cooling_roller_temp_k[i]:.3f}",
                f"{result.mean_belt_temp_k[i]:.3f}",
                f"{result.mean_belt_loading_mol_kg[i]:.6f}",
                f"{result.heater_power_w[i]:.2f}",
            ])


def plot_cycle_results(result, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 10), sharex=True)

    # Top panel: Temperatures with setpoint target
    ax1.plot(result.time_s, result.hot_roller_temp_k, label="Hot Roller (Regeneration)", color="#d95f02", lw=2.0)
    ax1.axhline(result.target_hot_roller_temp_k, color="#e41a1c", ls=":", lw=1.5, label=f"Target Setpoint ({result.target_hot_roller_temp_k - 273.15:.0f} °C)")
    ax1.plot(result.time_s, result.recovery_roller_temp_k, label="Intermediate Recovery Roller", color="#7570b3", lw=1.8)
    ax1.plot(result.time_s, result.cooling_roller_temp_k, label="Cooling Roller", color="#1b9e77", lw=1.8)
    ax1.plot(result.time_s, result.mean_belt_temp_k, label="Mean Belt Temperature", color="#e7298a", ls="--")
    ax1.set_ylabel("Temperature (K)")
    ax1.set_title("DAC Continuous Cycle Simulation — Temperature, Power, and Loading")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right", framealpha=0.9, fontsize=9)

    # Middle panel: Heater Electrical Power
    ax2.plot(result.time_s, result.heater_power_w, label="Heater Power (W)", color="#ff7f00", lw=1.8)
    ax2.axhline(result.average_heater_power_w, color="#377eb8", ls="--", lw=1.5, label=f"Avg Power ({result.average_heater_power_w:.1f} W)")
    ax2.set_ylabel("Power (W)")
    ax2.set_ylim(-10.0, 520.0)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="upper right", framealpha=0.9, fontsize=9)

    # Bottom panel: Mean sorbent loading
    ax3.plot(result.time_s, result.mean_belt_loading_mol_kg, label="Mean Sorbent Loading (mol CO2/kg)", color="#386cb0", lw=2.0)
    ax3.set_xlabel("Time (s)")
    ax3.set_ylabel("CO2 Loading (mol/kg)")
    ax3.grid(True, alpha=0.3)
    ax3.legend(loc="lower right", framealpha=0.9, fontsize=9)

    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def main() -> None:
    assumptions = load_yaml(ASSUMPTIONS_PATH)
    sorbent_props = SorbentProperties.from_assumptions(assumptions)
    belt = DiscretizedBelt.from_assumptions(
        assumptions,
        num_segments=50,
        initial_temperature_k=298.15,
        initial_loading_mol_kg=0.08,
    )

    # Run for 990 seconds (one complete revolution of the 1.98m loop at 2mm/s)
    duration_s = 990.0
    result = run_cycle_simulation(
        belt=belt,
        sorbent_props=sorbent_props,
        duration_s=duration_s,
        time_step_s=0.1,
        heater_power_w=500.0,
        target_hot_roller_temp_k=378.15,
        heater_controller="pid",
        fan_airflow_m3_h=150.0,
        air_co2_concentration_g_m3=0.72,
        ambient_temperature_k=298.15,
        fluid_flow_l_min=0.5,
        fluid_inlet_temperature_k=305.0,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_file = OUTPUT_DIR / "dac_cycle_history.csv"
    json_file = OUTPUT_DIR / "dac_cycle_report.json"
    plot_file = OUTPUT_DIR / "dac_cycle_plot.png"

    export_cycle_csv(result, csv_file)
    plot_cycle_results(result, plot_file)

    report_dict = {
        "simulation_duration_s": result.duration_s,
        "temperature_control": {
            "controller_type": "pid",
            "initial_temperature_k": round(result.initial_hot_roller_temp_k, 3),
            "target_temperature_k": round(result.target_hot_roller_temp_k, 3),
            "final_temperature_k": round(result.hot_roller_temp_k[-1], 3),
            "max_hot_roller_temp_k": round(result.max_hot_roller_temp_k, 3),
            "min_hot_roller_temp_k": round(result.min_hot_roller_temp_k, 3),
            "temperature_overshoot_k": round(result.temperature_overshoot_k, 3),
            "final_setpoint_error_k": round(result.final_setpoint_error_k, 3),
            "average_heater_power_w": round(result.average_heater_power_w, 2),
            "maximum_heater_power_w": 500.0,
        },
        "co2_mass_balance": {
            "air_fed_kg": result.co2_air_fed_kg,
            "captured_kg": result.co2_captured_kg,
            "untreated_air_kg": result.co2_air_untreated_kg,
            "released_during_regeneration_kg": result.co2_released_kg,
            "sorbent_initial_kg": result.co2_sorbent_initial_kg,
            "sorbent_final_kg": result.co2_sorbent_final_kg,
            "sorbent_accumulation_kg": result.co2_sorbent_delta_kg,
            "mass_balance_residual_kg": result.mass_balance_residual_kg,
            "total_co2_residual_kg": result.total_co2_balance_residual_kg,
        },
        "thermal_energy_balance": {
            "heater_input_j": result.heater_energy_j,
            "ambient_exchange_j": result.ambient_energy_j,
            "fluid_advective_input_j": result.fluid_energy_j,
            "fluid_heat_recovered_j": result.fluid_heat_recovered_j,
            "sensible_change_j": result.sensible_energy_change_j,
            "desorption_heat_j": result.desorption_energy_j,
            "total_energy_input_j": result.total_energy_input_j,
            "total_energy_absorbed_j": result.total_energy_absorbed_j,
            "energy_balance_residual_j": result.energy_balance_residual_j,
        },
        "performance_kpis": {
            "predicted_capture_rate_g_h": round(result.capture_rate_g_h, 4),
            "gross_specific_thermal_energy_mj_kg": round(result.specific_thermal_energy_mj_kg, 2),
            "gross_specific_thermal_energy_mwh_t": round(result.specific_thermal_energy_mwh_t, 2),
            "net_specific_thermal_energy_mj_kg": round(result.net_specific_thermal_energy_mj_kg, 2),
            "net_specific_thermal_energy_mwh_t": round((result.net_specific_thermal_energy_mj_kg * 1e6 / 3.6e9) * 1000.0, 2),
            "heat_recovery_ratio": round(result.heat_recovery_ratio, 4),
            "reaction_minimum_enthalpy_mwh_t": 1.60,
        },
        "final_temperatures_k": {
            "hot_roller": round(result.hot_roller_temp_k[-1], 3),
            "recovery_roller": round(result.recovery_roller_temp_k[-1], 3),
            "cooling_roller": round(result.cooling_roller_temp_k[-1], 3),
            "mean_belt": round(result.mean_belt_temp_k[-1], 3),
        },
    }

    with json_file.open("w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)

    print("\n" + "=" * 65)
    print("DAC FULL-CYCLE COUPLED SIMULATION COMPLETED (WITH TEMPERATURE CONTROL)")
    print("=" * 65)
    print(f"Duration: {result.duration_s:.1f} s (1.0 full loop revolution)")
    print(f"Hot Roller Temp: Target {result.target_hot_roller_temp_k:.2f} K ({result.target_hot_roller_temp_k - 273.15:.1f} °C) | Init {result.initial_hot_roller_temp_k:.2f} K | Final {result.hot_roller_temp_k[-1]:.2f} K")
    print(f"Overshoot: +{result.temperature_overshoot_k:.2f} K | Final Setpoint Error: {result.final_setpoint_error_k:+.2f} K")
    print(f"Average Heater Power: {result.average_heater_power_w:.1f} W (Throttled from 500 W max)")
    print(f"Predicted Capture Rate: {result.capture_rate_g_h:.3f} g CO2/h")
    print(f"CO2 Captured: {result.co2_captured_kg * 1000.0:.3f} g")
    print(f"CO2 Released in Regen: {result.co2_released_kg * 1000.0:.3f} g")
    print(f"CO2 Mass Balance Residual: {result.mass_balance_residual_kg:.3e} kg")
    print(f"Thermal Energy Input: {result.total_energy_input_j / 1e3:.2f} kJ")
    print(f"Fluid Heat Recovered: {result.fluid_heat_recovered_j / 1e3:.2f} kJ")
    print(f"Heat Recovery Ratio: {result.heat_recovery_ratio * 100.0:.1f}%")
    print(f"Energy Balance Residual: {result.energy_balance_residual_j:.3e} J")
    print(f"Gross Specific Thermal Energy: {result.specific_thermal_energy_mwh_t:.2f} MWh/t CO2")
    print(f"Net Specific Thermal Energy: {result.net_specific_thermal_energy_mj_kg:.2f} MJ/kg CO2")
    print(f"CSV exported: {csv_file}")
    print(f"JSON report: {json_file}")
    print(f"Plot saved: {plot_file}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
