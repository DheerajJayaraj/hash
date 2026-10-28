import pytest

from dac_sim.reporting import build_energy_report


@pytest.fixture
def sample_result():
    return {
        "time_s": [0.0, 10.0],
        "temperature_history_k": {
            "hot_roller": [350.0, 348.0],
            "belt_sorbent": [320.0, 321.0],
        },
        "external_energy_j": 500.0,
        "ambient_energy_j": -200.0,
        "total_internal_energy_change_j": 300.0,
        "energy_balance_error_j": 0.0,
    }


def test_report_calculates_duration_and_total_energy(sample_result):
    report = build_energy_report(sample_result)

    assert report["duration_s"] == pytest.approx(10.0)
    assert report["total_energy_input_j"] == pytest.approx(300.0)
    assert report["stored_energy_change_j"] == pytest.approx(300.0)


def test_report_contains_final_temperatures(sample_result):
    report = build_energy_report(sample_result)

    assert report["final_temperatures_k"] == {
        "hot_roller": 348.0,
        "belt_sorbent": 321.0,
    }


def test_report_rejects_missing_fields(sample_result):
    del sample_result["ambient_energy_j"]

    with pytest.raises(ValueError, match="missing fields"):
        build_energy_report(sample_result)


def test_report_rejects_non_finite_energy(sample_result):
    sample_result["external_energy_j"] = float("nan")

    with pytest.raises(ValueError, match="finite number"):
        build_energy_report(sample_result)


def test_report_rejects_mismatched_temperature_history(sample_result):
    sample_result["temperature_history_k"]["hot_roller"] = [350.0]

    with pytest.raises(ValueError, match="must match time_s"):
        build_energy_report(sample_result)


def test_report_rejects_invalid_final_temperature(sample_result):
    sample_result["temperature_history_k"]["hot_roller"][-1] = 0.0

    with pytest.raises(ValueError, match="above zero K"):
        build_energy_report(sample_result)
