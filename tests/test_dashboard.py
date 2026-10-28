"""Tests for the live dashboard backend, API endpoints, and validation."""

import json
import threading
import urllib.request
import urllib.error
import pytest

from dac_sim.dashboard import (
    DEFAULT_PARAMS,
    validate_dashboard_params,
    run_simulation_api,
    start_dashboard_server,
)


def test_validate_dashboard_params():
    # Valid default params
    clean = validate_dashboard_params(DEFAULT_PARAMS)
    assert clean["duration_s"] == 990.0
    assert clean["heater_controller"] == "pid"

    # Out of range duration
    with pytest.raises(ValueError, match="duration_s"):
        validate_dashboard_params({"duration_s": -50.0})

    # Out of range temperature
    with pytest.raises(ValueError, match="target_hot_roller_temp_c"):
        validate_dashboard_params({"target_hot_roller_temp_c": 200.0})

    # Invalid controller mode
    with pytest.raises(ValueError, match="Invalid controller mode"):
        validate_dashboard_params({"heater_controller": "quantum"})

    # Non-numeric input
    with pytest.raises(ValueError, match="must be a valid number"):
        validate_dashboard_params({"belt_speed_mm_s": "fast"})


def test_run_simulation_api_fast():
    # Fast 20s run to test full data packaging
    params = dict(DEFAULT_PARAMS)
    params["duration_s"] = 20.0
    params["time_step_s"] = 0.1

    data = run_simulation_api(params)

    assert data["status"] == "success"
    assert "kpis" in data
    assert "charts" in data
    assert "methanol" in data
    assert "csv_text" in data
    assert "plot_base64" in data

    kpis = data["kpis"]
    assert kpis["duration_s"] == 20.0
    assert kpis["capture_rate_g_h"] > 0.0
    assert kpis["hot_roller_final_c"] > 50.0
    assert kpis["average_heater_power_w"] > 0.0

    charts = data["charts"]
    assert len(charts["time_s"]) > 0
    assert len(charts["hot_roller_temp_c"]) == len(charts["time_s"])
    assert len(charts["heater_power_w"]) == len(charts["time_s"])

    meth = data["methanol"]
    assert meth["enabled"] is True
    assert meth["methanol_yield_g_h"] > 0.0
    assert meth["h2_demand_g_h"] > 0.0
    assert meth["electrolysis_power_w"] > 0.0


@pytest.fixture(scope="module")
def dashboard_server():
    port = 8059
    server = start_dashboard_server(host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def test_dashboard_http_endpoints(dashboard_server):
    base_url = dashboard_server

    # 1. GET /
    with urllib.request.urlopen(f"{base_url}/") as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "Heat-Linked Roller Belt DAC Simulation" in content
        assert "Zone 1: Ambient Adsorption" in content

    # 2. GET /api/baseline
    with urllib.request.urlopen(f"{base_url}/api/baseline") as resp:
        assert resp.status == 200
        baseline = json.loads(resp.read().decode("utf-8"))
        assert baseline["heater_power_w"] == 500.0
        assert baseline["heater_controller"] == "pid"

    # 3. POST /api/simulate (valid)
    payload = json.dumps({"duration_s": 15.0, "time_step_s": 0.1}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/simulate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode("utf-8"))
        assert res["status"] == "success"
        assert res["kpis"]["duration_s"] == 15.0

    # 4. POST /api/simulate (invalid parameters -> 400 Bad Request)
    bad_payload = json.dumps({"duration_s": -100.0}).encode("utf-8")
    bad_req = urllib.request.Request(
        f"{base_url}/api/simulate",
        data=bad_payload,
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(bad_req)
    assert exc_info.value.code == 400

    # 5. GET /api/export/csv
    with urllib.request.urlopen(f"{base_url}/api/export/csv") as resp:
        assert resp.status == 200
        csv_text = resp.read().decode("utf-8")
        assert "time_s,hot_roller_temp_k" in csv_text

    # 6. GET /api/export/json
    with urllib.request.urlopen(f"{base_url}/api/export/json") as resp:
        assert resp.status == 200
        json_data = json.loads(resp.read().decode("utf-8"))
        assert json_data["status"] == "success"

    # 7. GET /api/export/plot
    with urllib.request.urlopen(f"{base_url}/api/export/plot") as resp:
        assert resp.status == 200
        img_bytes = resp.read()
        assert img_bytes[:8] == b"\x89PNG\r\n\x1a\n"

    # 8. GET /nonexistent -> 404
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{base_url}/nonexistent")
    assert exc_info.value.code == 404
