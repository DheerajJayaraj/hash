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
        ])
        for i in range(len(result.time_s)):
            writer.writerow([
                f"{result.time_s[i]:.2f}",
                f"{result.hot_roller_temp_k[i]:.3f}",
                f"{result.recovery_roller_temp_k[i]:.3f}",
                f"{result.cooling_roller_temp_k[i]:.3f}",
                f"{result.mean_belt_temp_k[i]:.3f}",
                f"{result.mean_belt_loading_mol_kg[i]:.6f}",
            ])


def plot_cycle_results(result, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    # Top panel: Temperatures
    ax1.plot(result.time_s, result.hot_roller_temp_k, label="Hot Roller (Regeneration)", color="#d95f02", lw=1.8)
    ax1.plot(result.time_s, result.recovery_roller_temp_k, label="Intermediate Recovery Roller", color="#7570b3", lw=1.8)
    ax1.plot(result.time_s, result.cooling_roller_temp_k, label="Cooling Roller", color="#1b9e77", lw=1.8)
    ax1.plot(result.time_s, result.mean_belt_temp_k, label="Mean Belt Temperature", color="#e7298a", ls="--")
    ax1.set_ylabel("Temperature (K)")
    ax1.set_title("DAC Cycle Simulation — Thermal History and Sorbent Loading")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right", framealpha=0.9)

    # Bottom panel: Mean loading
    ax2.plot(result.time_s, result.mean_belt_loading_mol_kg, label="Mean Sorbent Loading (mol CO2/kg)", color="#386cb0", lw=2.0)
    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("CO2 Loading (mol/kg)")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="lower right", framealpha=0.9)

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

    # Run for 300 seconds (~0.3 complete revolution to evaluate transient cycle dynamics)
    duration_s = 300.0
    result = run_cycle_simulation(
        belt=belt,
        sorbent_props=sorbent_props,
        duration_s=duration_s,
        time_step_s=0.1,
        heater_power_w=500.0,
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
            "predicted_capture_rate_g_h": result.capture_rate_g_h,
            "specific_thermal_energy_mj_kg": result.specific_thermal_energy_mj_kg,
            "specific_thermal_energy_mwh_t": result.specific_thermal_energy_mwh_t,
            "net_specific_thermal_energy_mj_kg": result.net_specific_thermal_energy_mj_kg,
            "heat_recovery_ratio": result.heat_recovery_ratio,
        },
        "final_temperatures_k": {
            "hot_roller": result.hot_roller_temp_k[-1],
            "recovery_roller": result.recovery_roller_temp_k[-1],
            "cooling_roller": result.cooling_roller_temp_k[-1],
            "mean_belt": result.mean_belt_temp_k[-1],
        },
    }

    with json_file.open("w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)

    print("\n" + "=" * 60)
    print("DAC FULL-CYCLE COUPLED SIMULATION COMPLETED")
    print("=" * 60)
    print(f"Duration: {result.duration_s:.1f} s")
    print(f"Predicted Capture Rate: {result.capture_rate_g_h:.3f} g CO2/h")
    print(f"CO2 Captured: {result.co2_captured_kg * 1000.0:.3f} g")
    print(f"CO2 Released in Regen: {result.co2_released_kg * 1000.0:.3f} g")
    print(f"CO2 Mass Balance Residual: {result.mass_balance_residual_kg:.3e} kg")
    print(f"Thermal Energy Input: {result.total_energy_input_j / 1e3:.2f} kJ")
    print(f"Fluid Heat Recovered: {result.fluid_heat_recovered_j / 1e3:.2f} kJ")
    print(f"Heat Recovery Ratio: {result.heat_recovery_ratio * 100.0:.1f}%")
    print(f"Energy Balance Residual: {result.energy_balance_residual_j:.3e} J")
    print(f"Specific Thermal Energy: {result.specific_thermal_energy_mwh_t:.2f} MWh/t CO2")
    print(f"Net Specific Thermal Energy: {result.net_specific_thermal_energy_mj_kg:.2f} MJ/kg CO2")
    print(f"CSV exported: {csv_file}")
    print(f"JSON report: {json_file}")
    print(f"Plot saved: {plot_file}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
