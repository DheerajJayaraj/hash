"""Plot DAC thermal simulation data to a PNG file."""

from pathlib import Path
import csv

import matplotlib
matplotlib.use("Agg")  # No Tkinter/Tcl dependency.

import matplotlib.pyplot as plt

input_path = Path("outputs/thermal_history.csv")
output_path = Path("outputs/thermal_history.png")

if not input_path.exists():
    raise FileNotFoundError(f"CSV file not found: {input_path}")

with input_path.open("r", newline="", encoding="utf-8-sig") as file:
    reader = csv.DictReader(file)
    columns = reader.fieldnames
    rows = list(reader)

if not rows or not columns or "time_s" not in columns:
    raise ValueError("CSV is empty or missing the time_s column.")

time_s = [float(row["time_s"]) for row in rows]

fig, ax = plt.subplots(figsize=(10, 6))

for column in columns:
    if column == "time_s":
        continue
    temperatures = [float(row[column]) for row in rows]
    ax.plot(time_s, temperatures, label=column.replace("_", " ").title())

ax.set_xlabel("Time (s)")
ax.set_ylabel("Temperature (K)")
ax.set_title("DAC Prototype Thermal Simulation")
ax.grid(True, alpha=0.3)
ax.legend()
fig.tight_layout()

output_path.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(output_path, dpi=160)
plt.close(fig)

print(f"Plot saved to: {output_path.resolve()}")
print(f"Data points: {len(time_s)}")
