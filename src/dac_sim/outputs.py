"""Export thermal simulation results to CSV."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def export_temperature_history_csv(
    result: dict[str, Any],
    output_path: str | Path,
) -> Path:
    """Write simulation timestamps and node temperatures to a CSV file."""
    times = result.get("time_s")
    histories = result.get("temperature_history_k")

    if not isinstance(times, list) or not times:
        raise ValueError("Result must contain a non-empty time_s list.")
    if not isinstance(histories, dict) or not histories:
        raise ValueError("Result must contain temperature histories.")

    for name, values in histories.items():
        if not isinstance(values, list) or len(values) != len(times):
            raise ValueError(
                f"Temperature history for {name!r} must match the time list."
            )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["time_s", *histories.keys()])

        for index, time_s in enumerate(times):
            writer.writerow(
                [time_s, *(histories[name][index] for name in histories)]
            )

    return path
