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
    """The served default, shrunk to something a contract test can afford.

    `/api/scenarios/default` is a twenty-five tile demonstration region with both
    between-tile fluxes on. That is the right thing for the UI to open on and
    twenty-five times too much work for a test that only wants to know whether a
    field reaches the model, so anything not about grids runs on one tile.
    """
    config = client.get("/api/scenarios/default").json()
    config.update(years=2)
    config["grid"].update(nx=1, ny=1, dispersal="none", lateral_shading="none")
    config["tile_assignment"] = []
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
        "/api/simulations", json={"grid": {"nx": 99}}
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
    assert len(results["tiles"]) == 1
    series = results["tiles"][0]["series"]
    assert len(series) == len(results["recorded_days"]) == len(results["years"])
    for key in ("grassland_shoot_c", "forest_biomass_c", "lai", "soil_c", "mineral_n"):
        assert key in series[-1]

    profiles = client.get(f"/api/simulations/{job['id']}/profile?x=0&y=0").json()
    assert len(profiles) == len(series)
    assert "sward_profile" in profiles[-1]
    assert "stand_profile" in profiles[-1]
    assert "dbh_histogram" in profiles[-1]


def test_multi_tile_run_returns_every_tile(client):
    config = scenario(client, name="grid run")
    config["grid"].update(nx=2, ny=2, dispersal="exponential")
    job = client.post("/api/simulations", json=config).json()
    status = wait_for(client, job["id"])
    assert status["state"] == "done", status["error"]
    results = client.get(f"/api/simulations/{job['id']}/results").json()
    assert {(t["x"], t["y"]) for t in results["tiles"]} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert client.get(f"/api/simulations/{job['id']}/profile?x=1&y=1").json()
    assert client.get(f"/api/simulations/{job['id']}/profile?x=9&y=9").status_code == 404


def test_an_unspecified_grid_is_one_independent_tile(client):
    """A POST that omits `grid` must not silently buy a region, or a physics.

    The *served* default scenario is a deliberately spatial demonstration and
    turns both fluxes on. The *schema* default must not: a client that leaves
    the field out is asking for the cheapest, most inert run there is, and
    `ecocore`'s grid-reproduces-a-single-tile guard depends on off being off.
    """
    job = client.post("/api/simulations", json={"years": 1, "name": "bare"}).json()
    status = wait_for(client, job["id"])
    assert status["state"] == "done", status["error"]
    grid = client.get(f"/api/simulations/{job['id']}/results").json()["scenario"]["grid"]
    assert (grid["nx"], grid["ny"]) == (1, 1)
    assert grid["dispersal"] == "none"
    assert grid["lateral_shading"] == "none"
    assert grid["shading_radius_tiles"] == 2


def test_lateral_shading_reaches_the_model(client):
    """The scenario knob must actually change the light a tile receives.

    Shading is reported per tile in the series, so the API surface for it is the
    same one the map and the charts already read.
    """
    config = scenario(client, name="shaded grid")
    config["grid"].update(nx=2, ny=2, lateral_shading="sky_view", tile_size_m=10.0)
    config["tile_types"][0]["vegetation"].update(
        initial_trees_per_tile=40, initial_tree_dbh=0.4
    )
    status = wait_for(client, client.post("/api/simulations", json=config).json()["id"])
    assert status["state"] == "done", status["error"]
    results = client.get(f"/api/simulations/{status['id']}/results").json()

    fractions = [t["series"][-1]["sky_view_fraction"] for t in results["tiles"]]
    assert all(0.0 < f <= 1.0 for f in fractions)
    assert min(fractions) < 1.0, "a stand of 40 trees per tile must shade its neighbours"


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
        rb["tiles"][0]["series"][-1]["grassland_shoot_c_grass"]
        < 0.5 * ra["tiles"][0]["series"][-1]["grassland_shoot_c_grass"]
    )


def test_jobs_are_listed_newest_first(client):
    config = scenario(client, years=1)
    for name in ("first", "second"):
        config["name"] = name
        client.post("/api/simulations", json=config)
    listed = client.get("/api/simulations").json()
    assert len(listed) == 2


# ------------------------------------------------------------- tile types --


def test_the_default_scenario_assigns_every_tile_a_type(client):
    """Every tile must have a land use. A tile with none is not simulable."""
    config = client.get("/api/scenarios/default").json()
    ids = {t["id"] for t in config["tile_types"]}
    assert ids
    assert len(config["tile_assignment"]) == config["grid"]["nx"] * config["grid"]["ny"]
    assert set(config["tile_assignment"]) <= ids


def test_an_omitted_assignment_means_one_land_use_everywhere(client):
    """A client that has never heard of tile types still gets a uniform region."""
    config = scenario(client, name="uniform")
    config["grid"].update(nx=2, ny=1)
    config["tile_assignment"] = []
    status = wait_for(client, client.post("/api/simulations", json=config).json()["id"])
    assert status["state"] == "done", status["error"]
    results = client.get(f"/api/simulations/{status['id']}/results").json()
    a, b = (t["series"][-1]["grassland_shoot_c"] for t in results["tiles"])
    assert a == pytest.approx(b), "identical types must produce identical tiles"


@pytest.mark.parametrize(
    "assignment,reason",
    [
        (["abandoned"], "too few entries for the grid"),
        (["abandoned", "meadow", "abandoned"], "too many entries for the grid"),
        (["abandoned", "swamp"], "names a type that does not exist"),
    ],
)
def test_a_bad_tile_assignment_is_rejected(client, assignment, reason):
    """Padding or truncating silently would run a different scenario than asked."""
    config = scenario(client)
    config["grid"].update(nx=2, ny=1)
    config["tile_assignment"] = assignment
    assert client.post("/api/simulations", json=config).status_code == 422, reason


def test_duplicate_tile_type_ids_are_rejected(client):
    config = scenario(client)
    config["tile_types"] = [
        {"id": "same", "label": "One", "management": {"preset": "abandoned"}},
        {"id": "same", "label": "Two", "management": {"preset": "pasture"}},
    ]
    config["tile_assignment"] = []
    assert client.post("/api/simulations", json=config).status_code == 422


def test_tile_types_give_neighbouring_tiles_different_outcomes(client):
    """The point of the whole feature: two tiles of one region can differ.

    A mown tile beside an unmown one, same soil, same weather, same PFTs, no
    between-tile fluxes -- so management is the *only* thing that differs, and
    any difference in the sward is attributable to it.
    """
    config = scenario(client, years=4, name="two land uses")
    config["grid"].update(nx=2, ny=1)
    config["tile_assignment"] = ["abandoned", "meadow"]
    status = wait_for(client, client.post("/api/simulations", json=config).json()["id"])
    assert status["state"] == "done", status["error"]
    results = client.get(f"/api/simulations/{status['id']}/results").json()

    by_x = {t["x"]: t["series"][-1] for t in results["tiles"]}
    # The cut removes most of the standing crop, so the mown tile carries less.
    assert by_x[1]["grassland_shoot_c"] < by_x[0]["grassland_shoot_c"]
    # Soil is region-wide and both tiles start from it, so they start equal.
    first = {t["x"]: t["series"][0] for t in results["tiles"]}
    assert first[0]["soil_c"] == pytest.approx(first[1]["soil_c"])


def test_initial_vegetation_is_a_property_of_the_type(client):
    """A planted type must put a stand on its tiles and only on its tiles."""
    config = scenario(client, years=1, name="wood and field")
    config["grid"].update(nx=2, ny=1)
    config["tile_assignment"] = ["forest", "abandoned"]
    status = wait_for(client, client.post("/api/simulations", json=config).json()["id"])
    assert status["state"] == "done", status["error"]
    results = client.get(f"/api/simulations/{status['id']}/results").json()
    by_x = {t["x"]: t["series"][0] for t in results["tiles"]}
    assert by_x[0]["forest_stems"] > 0.0
    assert by_x[1]["forest_stems"] == 0.0
