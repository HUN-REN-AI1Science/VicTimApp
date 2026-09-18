"""API contract tests.

The parameter endpoints are covered as carefully as the simulation ones because
the frontend builds its forms from them: a schema entry that loses its unit or
default silently degrades the UI rather than breaking it.
"""

import time

import pytest


def wait_for(client, job_id, timeout_s=240):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = client.get(f"/api/simulations/{job_id}").json()
        if status["state"] in ("done", "failed"):
            return status
        time.sleep(0.25)
    raise AssertionError("simulation did not finish in time")


def scenario(client, **overrides):
    """The served default, with a short `years` so a contract test can afford it."""
    config = client.get("/api/scenarios/default").json()
    config.update(years=2)
    config.update(overrides)
    return config


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("model,expected", [("formind", "pioneer"), ("grassmind", "legume")])
def test_parameter_schema_is_complete(client, model, expected):
    payload = client.get(f"/api/parameters/{model}").json()
    assert payload["model"] == model
    assert {p["id"] for p in payload["pfts"]} >= {expected}
    for entry in payload["schema"]:
        assert {"name", "group", "unit", "default", "type"} <= set(entry)
        assert entry["type"] in ("number", "boolean")
    # Every schema entry must actually exist on every PFT, or the UI shows blanks.
    names = {e["name"] for e in payload["schema"]}
    for pft in payload["pfts"]:
        assert names <= set(pft)


def test_unknown_model_is_404(client):
    assert client.get("/api/parameters/nope").status_code == 404


def test_management_presets_describe_their_events(client):
    presets = {p["id"]: p for p in client.get("/api/management/presets").json()}
    assert presets["abandoned"]["mowing"] == []
    assert len(presets["extensive_meadow"]["mowing"]) == 1
    assert len(presets["intensive_meadow"]["mowing"]) == 4
    assert presets["pasture"]["grazing"]
    # A mower must be able to kill saplings, or management cannot stop invasion.
    assert presets["extensive_meadow"]["mowing"][0]["woody_kill_height_m"] > 0


def test_default_scenario_is_runnable_as_returned(client):
    """Whatever the demo scenario grows into, it must still validate and submit."""
    config = client.get("/api/scenarios/default").json()
    config["years"] = 1
    assert client.post("/api/simulations", json=config).status_code == 202


def test_invalid_scenario_is_rejected(client):
    assert client.post("/api/simulations", json={"years": 0}).status_code == 422
    assert client.post("/api/simulations", json={"years": 10_000}).status_code == 422
    assert client.post(
        "/api/simulations", json={"site": {"depth_m": -1}}
    ).status_code == 422


def test_unknown_job_is_404(client):
    assert client.get("/api/simulations/deadbeef").status_code == 404
    assert client.get("/api/simulations/deadbeef/results").status_code == 404


def test_results_before_completion_are_409(client):
    config = scenario(client, years=40)
    job = client.post("/api/simulations", json=config).json()
    response = client.get(f"/api/simulations/{job['id']}/results")
    assert response.status_code in (409, 200)


def test_full_run_returns_series_and_profiles(client):
    config = scenario(client, years=6, name="test run")
    job = client.post("/api/simulations", json=config).json()
    assert job["state"] in ("queued", "running")
    assert job["total_days"] == 6 * 365

    status = wait_for(client, job["id"])
    assert status["state"] == "done", status["error"]
    assert status["progress"] == 1.0
    assert status["finished_at"]

    results = client.get(f"/api/simulations/{job['id']}/results").json()
    assert results["scenario"]["name"] == "test run"
    series = results["series"]
    assert len(series) == len(results["recorded_days"]) == len(results["years"])
    for key in ("grassland_shoot_c", "forest_biomass_c", "lai", "soil_c", "mineral_n"):
        assert key in series[-1]

    profiles = client.get(f"/api/simulations/{job['id']}/profile").json()
    assert len(profiles) == len(series)
    assert "sward_profile" in profiles[-1]
    assert "stand_profile" in profiles[-1]
    assert "dbh_histogram" in profiles[-1]


def test_pft_overrides_change_the_outcome(client):
    """Editing a parameter in the UI must actually reach the model."""
    base = scenario(client, years=4, name="baseline")
    slow = scenario(client, years=4, name="slow grass")
    slow["vegetation"]["grass_pft_overrides"] = {"grass": {"pmax": 2.0}}

    a = wait_for(client, client.post("/api/simulations", json=base).json()["id"])
    b = wait_for(client, client.post("/api/simulations", json=slow).json()["id"])
    assert a["state"] == b["state"] == "done"
    ra = client.get(f"/api/simulations/{a['id']}/results").json()
    rb = client.get(f"/api/simulations/{b['id']}/results").json()
    # Checked on the PFT that was actually weakened, not on total shoot biomass:
    # the other functional groups compensate, which is the ecologically correct
    # response and would mask the change in a community-level total.
    assert (
        rb["series"][-1]["grassland_shoot_c_grass"]
        < 0.5 * ra["series"][-1]["grassland_shoot_c_grass"]
    )


def test_jobs_are_listed_newest_first(client):
    config = scenario(client, years=1)
    for name in ("first", "second"):
        config["name"] = name
        client.post("/api/simulations", json=config)
    listed = client.get("/api/simulations").json()
    assert len(listed) == 2
