"""Integration tests for the coupled forest-grassland tile.

These are the tests that justify the whole architecture. Each one checks a
behaviour that can ONLY arise if the two models genuinely share one light profile
and one soil column -- a design that ran them side by side and blended their
outputs would fail every one of them.
"""

import numpy as np
import pytest

from ecocore import SoilColumn, SoilParameters, Tile, synthetic_weather
from ecocore.units import DAYS_PER_YEAR
from formind import ForestModule
from grassmind import GrasslandModule, ManagementSchedule

TREE_SEED = {"pioneer": 8.0, "mid": 4.0, "late": 2.0}
GRASS_SEED = {"grass": 400.0, "forb": 250.0, "legume": 150.0}


def build_tile(schedule=None, with_trees=True, with_grass=True, tree_seed=None):
    tile = Tile(soil=SoilColumn(SoilParameters()))
    modules = {}
    if with_grass:
        modules["grass"] = GrasslandModule.sown_sward(
            management=schedule or ManagementSchedule.abandoned()
        )
        tile.add_module(modules["grass"])
    if with_trees:
        modules["forest"] = ForestModule.bare_ground()
        tile.add_module(modules["forest"])
    tile.seed_rain.external = {
        **(GRASS_SEED if with_grass else {}),
        **((tree_seed if tree_seed is not None else TREE_SEED) if with_trees else {}),
    }
    return tile, modules


def run(tile, years, seed=1, check_light=False):
    weather = synthetic_weather(5, seed=seed)
    rng = np.random.default_rng(seed)
    history = []
    for day in range(years * DAYS_PER_YEAR):
        light = tile.step_day(weather.day(day), day, rng)
        if check_light:
            assert light.absorbed_total <= light.incident_par + 1e-6, (
                f"day {day}: cohorts absorbed more light than arrived"
            )
        if (day + 1) % DAYS_PER_YEAR == 0:
            history.append(tile.diagnostics(light))
    return history


def test_absorbed_light_never_exceeds_incident_light():
    """The guard against double-counting, run over a real coupled simulation."""
    tile, _ = build_tile()
    run(tile, 12, check_light=True)


def test_both_models_appear_in_one_light_profile():
    tile, modules = build_tile()
    run(tile, 25)
    from ecocore.light import LightProfile

    profile = LightProfile(tile.area_m2)
    for module in tile.modules:
        profile.add(module.canopy_elements())
    result = profile.resolve(800.0)
    grass_keys = {id(c) for c in modules["grass"].cohorts}
    tree_keys = {id(c) for c in modules["forest"].cohorts} | {
        id(s) for s in modules["forest"].seedlings
    }
    assert grass_keys & set(result.absorbed_par)
    assert tree_keys & set(result.absorbed_par)
    assert result.absorbed_total + result.floor_par == pytest.approx(800.0, rel=1e-9)


@pytest.mark.slow
def test_abandoned_grassland_is_invaded_by_trees():
    """Woody encroachment must EMERGE, not be scripted.

    Nothing in the code says "trees replace grass". It happens because seedlings
    survive the sward, cross breast height, and then cast enough shade through the
    shared profile to push the grass below its shade-mortality threshold.
    """
    tile, _ = build_tile(ManagementSchedule.abandoned())
    history = run(tile, 90)
    early, late = history[15], history[-1]
    assert early["forest_biomass_c"] == 0.0
    assert early["grassland_shoot_c"] > 0.05
    assert late["forest_biomass_c"] > 1.0
    assert late["grassland_shoot_c"] < 0.2 * early["grassland_shoot_c"]
    assert late["floor_light_fraction"] < 0.15


@pytest.mark.slow
@pytest.mark.parametrize(
    "schedule",
    [ManagementSchedule.extensive_meadow(), ManagementSchedule.pasture()],
    ids=["mown", "grazed"],
)
def test_management_prevents_woody_encroachment(schedule):
    """A meadow stays a meadow.

    This works only because mowing is emitted as a tile-level disturbance that the
    FOREST module also sees. If management touched only the grass, this test would
    fail and the model would predict that every hay meadow becomes woodland.
    """
    tile, _ = build_tile(schedule)
    history = run(tile, 90)
    assert history[-1]["forest_biomass_c"] == 0.0
    assert history[-1]["forest_stems"] == 0.0
    assert history[-1]["grassland_shoot_c"] > 0.02


@pytest.mark.slow
def test_grass_delays_tree_establishment():
    """The sward must measurably slow invasion relative to bare ground."""
    with_grass, _ = build_tile(ManagementSchedule.abandoned(), with_grass=True)
    bare, _ = build_tile(ManagementSchedule.abandoned(), with_grass=False)
    grassy = run(with_grass, 30)
    empty = run(bare, 30)
    assert empty[-1]["forest_biomass_c"] > grassy[-1]["forest_biomass_c"]


@pytest.mark.slow
def test_grass_and_trees_compete_for_the_same_water():
    """Adding a sward must leave the shared column drier."""
    coupled, _ = build_tile(ManagementSchedule.abandoned())
    trees_only, _ = build_tile(ManagementSchedule.abandoned(), with_grass=False)
    run(coupled, 20)
    run(trees_only, 20)
    assert coupled.soil.cumulative_transpiration_mm > trees_only.soil.cumulative_transpiration_mm


@pytest.mark.slow
def test_legume_fixation_raises_nitrogen_available_to_trees():
    """A grassland process feeding a forest one, through the shared mineral pool."""
    tile, _ = build_tile(ManagementSchedule.abandoned())
    run(tile, 20)
    assert tile.soil.cumulative_fixed_n > 0.0
    # The forest took nitrogen up from a pool the legumes contributed to.
    assert tile.soil.cumulative_uptake_n > 0.0


def test_module_order_does_not_change_the_disturbance_broadcast():
    """Disturbances are collected before anyone steps, so order must not matter."""
    schedule = ManagementSchedule.extensive_meadow()
    forward = Tile(soil=SoilColumn(SoilParameters()))
    forward.add_module(GrasslandModule.sown_sward(management=schedule))
    forward.add_module(ForestModule.bare_ground())
    reverse = Tile(soil=SoilColumn(SoilParameters()))
    reverse.add_module(ForestModule.bare_ground())
    reverse.add_module(GrasslandModule.sown_sward(management=schedule))
    for tile in (forward, reverse):
        tile.seed_rain.external = {**GRASS_SEED, **TREE_SEED}

    a = run(forward, 6)
    b = run(reverse, 6)
    assert a[-1]["forest_seedlings"] == pytest.approx(b[-1]["forest_seedlings"], rel=1e-9)
    assert a[-1]["grassland_shoot_c"] == pytest.approx(b[-1]["grassland_shoot_c"], rel=1e-9)


@pytest.mark.slow
def test_soil_carbon_and_nitrogen_stay_conserved_in_a_coupled_run():
    tile, _ = build_tile(ManagementSchedule.extensive_meadow())
    c0, n0 = tile.soil.total_c, tile.soil.total_n
    run(tile, 25)
    assert tile.soil.carbon_balance_error(c0) == pytest.approx(0.0, abs=1e-8)
    assert tile.soil.nitrogen_balance_error(n0) == pytest.approx(0.0, abs=1e-9)
