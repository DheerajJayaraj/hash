import csv
import pytest

from dac_sim.outputs import export_temperature_history_csv


def test_export_writes_time_and_temperature_columns(tmp_path):
    result = {
        "time_s": [0.0, 1.0],
        "temperature_history_k": {
            "hot_roller": [378.15, 377.9],
            "belt_sorbent": [320.0, 321.0],
        },
    }

    path = export_temperature_history_csv(
        result, tmp_path / "thermal.csv"
    )

    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.reader(file))

    assert rows[0] == ["time_s", "hot_roller", "belt_sorbent"]
    assert rows[1] == ["0.0", "378.15", "320.0"]
    assert rows[2] == ["1.0", "377.9", "321.0"]


def test_export_creates_missing_parent_directory(tmp_path):
    result = {
        "time_s": [0.0],
        "temperature_history_k": {"node": [300.0]},
    }

    path = export_temperature_history_csv(
        result, tmp_path / "nested" / "folder" / "thermal.csv"
    )

    assert path.exists()


def test_export_rejects_empty_time_history(tmp_path):
    with pytest.raises(ValueError, match="non-empty time_s"):
        export_temperature_history_csv(
            {"time_s": [], "temperature_history_k": {"node": []}},
            tmp_path / "thermal.csv",
        )


def test_export_rejects_mismatched_history_length(tmp_path):
    result = {
        "time_s": [0.0, 1.0],
        "temperature_history_k": {"node": [300.0]},
    }

    with pytest.raises(ValueError, match="must match the time list"):
        export_temperature_history_csv(result, tmp_path / "thermal.csv")
