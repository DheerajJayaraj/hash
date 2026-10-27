"""Load and validate the DAC assumptions YAML file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dac_sim.validation import validate_register


def load_assumptions(path: str | Path) -> dict[str, Any]:
    """Load assumptions from YAML and validate their metadata and ranges."""
    assumptions_path = Path(path)

    if not assumptions_path.is_file():
        raise FileNotFoundError(
            f"Assumptions file does not exist: {assumptions_path}"
        )

    with assumptions_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    validate_register(data)
    return data


def get_value(
    register: dict[str, Any],
    parameter: str,
) -> Any:
    """Return the value of a named top-level project parameter."""
    try:
        return register["project"][parameter]["value"]
    except KeyError as exc:
        raise KeyError(f"Unknown assumption: {parameter}") from exc
