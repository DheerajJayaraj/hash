"""Run and report an illustrative DAC prototype thermal simulation."""

from pathlib import Path

import yaml

from dac_sim.prototype import build_prototype_network
from dac_sim.simulation import run_thermal_simulation
from dac_sim.outputs import export_temperature_history_csv
from dac_sim.reporting import build_energy_report

ROOT = Path(__file__).resolve().parents[1]
ASSUMPTIONS_PATH = ROOT / "assumptions.yaml"
THERMAL_MODEL_PATH = ROOT / "thermal_model.yaml"
OUTPUT_DIR = ROOT / "outputs"


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a YAML mapping.")

    return data


def main() -> None:
    assumptions = load_yaml(ASSUMPTIONS_PATH)
    thermal_model = load_yaml(THERMAL_MODEL_PATH)

    properties_config = thermal_model.get("thermal_properties", {})
    thermal_properties = {
        name: (
            values["mass_kg"],
            values["specific_heat_j_kg_k"],
        )
        for name, values in properties_config.items()
    }

    conductances_w_k = thermal_model["conductances_w_k"]
    ambient_loss_conductance_w_k = thermal_model[
        "ambient_loss_conductance_w_k"
    ]

    nodes, links, heater = build_prototype_network(
        assumptions=assumptions,
        thermal_properties=thermal_properties,
        conductances_w_k=conductances_w_k,
        belt_temperature_k=320.0,
    )

    project = assumptions["project"]
    prototype = project["prototype"]["value"]
    ambient_temperature_k = project["ambient_temperature"]["value"]

    result = run_thermal_simulation(
        nodes=nodes,
        links=links,
        duration_s=10.0,
        time_step_s=0.1,
        external_heat_w=heater,
        ambient_temperature_k=ambient_temperature_k,
        ambient_loss_conductance_w_k=ambient_loss_conductance_w_k,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = export_temperature_history_csv(
        result, OUTPUT_DIR / "thermal_history.csv"
    )

    import subprocess
    import sys

    plot_script = ROOT / "scripts" / "plot_thermal_history.py"
    subprocess.run(
        [sys.executable, str(plot_script)],
        cwd=ROOT,
        check=True,
    )

    report = build_energy_report(result)

    print("\nDAC thermal simulation")
    print("WARNING: Thermal masses and conductances are illustrative.")
    print(f"Prototype heater rating: {prototype['heater_power']:.1f} W")
    print(f"Simulated duration: {report['duration_s']:.2f} s")
    print(f"CSV: {csv_path}")
    print(f"PNG: {OUTPUT_DIR / 'thermal_history.png'}")
    print(f"External energy: {report['external_energy_j']:.3f} J")
    print(f"Ambient energy: {report['ambient_energy_j']:.3f} J")
    print(
        "Stored energy change: "
        f"{report['stored_energy_change_j']:.3f} J"
    )
    print(
        "Energy-balance error: "
        f"{report['energy_balance_error_j']:.9f} J"
    )

    print("\nFinal temperatures:")
    for name, temperature in report["final_temperatures_k"].items():
        print(f"  {name}: {temperature:.3f} K")

    print("\nSimulation completed.")


if __name__ == "__main__":
    main()
