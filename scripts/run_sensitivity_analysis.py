"""Parameter sensitivity analysis workflow for the Heat-Linked Roller Belt DAC."""

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
        return yaml.safe_load(file)


def run_sensitivity_sweep() -> list[dict]:
    assumptions = load_yaml(ASSUMPTIONS_PATH)
    base_props = SorbentProperties.from_assumptions(assumptions)

    # Cases: baseline, varying speed, varying heater, varying uptake rate, varying loop flow
    cases = [
        {"case": "Baseline (v=2mm/s, P=500W, uptake=0.065, flow=0.5L/min)", "speed": 0.002, "power": 500.0, "uptake": 0.065 / 60.0, "flow": 0.5},
        {"case": "Low Belt Speed (v=1mm/s)", "speed": 0.001, "power": 500.0, "uptake": 0.065 / 60.0, "flow": 0.5},
        {"case": "High Belt Speed (v=4mm/s)", "speed": 0.004, "power": 500.0, "uptake": 0.065 / 60.0, "flow": 0.5},
        {"case": "Low Heater Power (P=350W)", "speed": 0.002, "power": 350.0, "uptake": 0.065 / 60.0, "flow": 0.5},
        {"case": "High Heater Power (P=650W)", "speed": 0.002, "power": 650.0, "uptake": 0.065 / 60.0, "flow": 0.5},
        {"case": "Low Uptake Rate (0.0435 mmol/g/min)", "speed": 0.002, "power": 500.0, "uptake": 0.0435 / 60.0, "flow": 0.5},
        {"case": "High Uptake Rate (0.0870 mmol/g/min)", "speed": 0.002, "power": 500.0, "uptake": 0.0870 / 60.0, "flow": 0.5},
        {"case": "High Fluid Recovery Flow (1.0 L/min)", "speed": 0.002, "power": 500.0, "uptake": 0.065 / 60.0, "flow": 1.0},
    ]

    results = []
    duration_s = 150.0  # Fast, representative duration

    for c in cases:
        props = SorbentProperties(
            working_capacity_mol_kg=base_props.working_capacity_mol_kg,
            uptake_rate_mol_kg_s=c["uptake"],
            desorption_heat_j_kg=base_props.desorption_heat_j_kg,
            desorption_rate_s=base_props.desorption_rate_s,
            desorption_temp_onset_k=base_props.desorption_temp_onset_k,
            desorption_temp_peak_k=base_props.desorption_temp_peak_k,
            residual_capacity_fraction=base_props.residual_capacity_fraction,
        )
        belt = DiscretizedBelt.from_assumptions(
            assumptions,
            num_segments=36,
            initial_temperature_k=298.15,
            initial_loading_mol_kg=0.08,
        )
        belt.belt_speed_m_s = c["speed"]

        sim = run_cycle_simulation(
            belt=belt,
            sorbent_props=props,
            duration_s=duration_s,
            time_step_s=0.1,
            heater_power_w=c["power"],
            fan_airflow_m3_h=150.0,
            air_co2_concentration_g_m3=0.72,
            ambient_temperature_k=298.15,
            fluid_flow_l_min=c["flow"],
            fluid_inlet_temperature_k=305.0,
        )

        results.append({
            "case": c["case"],
            "belt_speed_mm_s": c["speed"] * 1000.0,
            "heater_power_w": c["power"],
            "uptake_rate_mmol_g_min": c["uptake"] * 60.0,
            "fluid_flow_l_min": c["flow"],
            "capture_rate_g_h": round(sim.capture_rate_g_h, 3),
            "specific_thermal_mwh_t": round(sim.specific_thermal_energy_mwh_t, 2),
            "net_specific_thermal_mj_kg": round(sim.net_specific_thermal_energy_mj_kg, 2),
            "heat_recovery_ratio_pct": round(sim.heat_recovery_ratio * 100.0, 1),
            "final_hot_roller_temp_k": round(sim.hot_roller_temp_k[-1], 2),
        })

    return results


def main() -> None:
    results = run_sensitivity_sweep()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = OUTPUT_DIR / "sensitivity_analysis.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    # Plot comparisons
    plot_path = OUTPUT_DIR / "sensitivity_analysis.png"
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    labels = [r["case"].split("(")[0].strip() for r in results]
    capture_rates = [r["capture_rate_g_h"] for r in results]
    specific_energies = [r["specific_thermal_mwh_t"] for r in results]

    y_pos = range(len(labels))
    ax1.barh(y_pos, capture_rates, color="#1f78b4", alpha=0.85)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(labels)
    ax1.invert_yaxis()
    ax1.set_xlabel("Capture Rate (g CO2/h)")
    ax1.set_title("Sensitivity: Predicted CO2 Capture Rate")
    ax1.grid(True, axis="x", alpha=0.3)

    ax2.barh(y_pos, specific_energies, color="#e31a1c", alpha=0.85)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(labels)
    ax2.invert_yaxis()
    ax2.set_xlabel("Specific Thermal Demand (MWh/t CO2)")
    ax2.set_title("Sensitivity: Thermal Energy Intensity")
    ax2.grid(True, axis="x", alpha=0.3)

    fig.tight_layout()
    fig.savefig(plot_path, dpi=160)
    plt.close(fig)

    print("\n" + "=" * 60)
    print("SENSITIVITY ANALYSIS COMPLETE")
    print("=" * 60)
    for r in results:
        print(
            f"{r['case']:<50} | "
            f"Capture: {r['capture_rate_g_h']:>5.2f} g/h | "
            f"Energy: {r['specific_thermal_mwh_t']:>5.2f} MWh/t"
        )
    print("=" * 60)
    print(f"CSV saved: {csv_path}")
    print(f"Plot saved: {plot_path}")


if __name__ == "__main__":
    main()
