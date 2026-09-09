"""Forest behaviour tests.

These check that the port reproduces the qualitative patterns a forest gap model
exists to produce -- succession, self-thinning, shade tolerance ranking -- rather
than checking numbers that would move with any recalibration.
"""

import numpy as np
import pytest

from ecocore import SoilColumn, SoilParameters, Tile, synthetic_weather
from ecocore.units import DAYS_PER_YEAR
from formind import ForestModule


def run_forest(years, seed=1, seeds_external=None, pfts=None):
    tile = Tile(soil=SoilColumn(SoilParameters()))
    forest = ForestModule.bare_ground(pfts)
    tile.add_module(forest)
    tile.seed_rain.external = seeds_external or {"pioneer": 8.0, "mid": 4.0, "late": 2.0}
    weather = synthetic_weather(5, seed=seed)
    rng = np.random.default_rng(seed)
    history = []
    for day in range(years * DAYS_PER_YEAR):
        tile.step_day(weather.day(day), day, rng)
        if (day + 1) % DAYS_PER_YEAR == 0:
            history.append(forest.diagnostics(tile.area_m2))
    return forest, tile, history


@pytest.mark.slow
def test_bare_ground_accumulates_biomass_and_closes_the_canopy():
    forest, tile, history = run_forest(60)
    biomass = [h["biomass_c"] for h in history]
    assert biomass[-1] > 50 * biomass[4]
    light = tile.step_day(synthetic_weather(1, seed=1).day(180), 180, np.random.default_rng(0))
    assert light.total_lai > 3.0
    assert light.floor_par / light.incident_par < 0.15


@pytest.mark.slow
def test_stand_self_thins_as_it_matures():
    """Stem number must fall while mean diameter rises -- the self-thinning law."""
    _, _, history = run_forest(90)
    peak = max(range(len(history)), key=lambda i: history[i]["stems"])
    assert history[-1]["stems"] < history[peak]["stems"]
    assert history[-1]["mean_dbh"] > history[peak]["mean_dbh"]


@pytest.mark.slow
def test_late_successional_types_replace_pioneers():
    _, _, history = run_forest(120)
    early = history[10]
    late = history[-1]
    assert early["biomass_c_pioneer"] > early["biomass_c_late"]
    assert late["biomass_c_late"] > late["biomass_c_pioneer"]


def test_seedlings_must_climb_to_breast_height_before_becoming_trees():
    """No tree may appear in the first years: the seedling bank is the bottleneck."""
    forest, _, history = run_forest(6)
    assert history[0]["stems"] == 0
    assert history[0]["seedlings"] > 0
    assert all(sd.height_m < 1.3 for sd in forest.seedlings)


def test_cohort_count_stays_bounded():
    """Merging must stop annual recruitment from growing the cohort list forever."""
    _, _, history = run_forest(60)
    assert history[-1]["cohorts"] < 80
    assert history[-1]["seedling_cohorts"] < 80


def test_planted_stand_grows_without_any_seed_input():
    tile = Tile(soil=SoilColumn(SoilParameters()))
    forest = ForestModule.bare_ground()
    forest.seed_stand("mid", n=40, dbh=0.05)
    tile.add_module(forest)
    weather = synthetic_weather(2, seed=3)
    rng = np.random.default_rng(3)
    start = forest.diagnostics(tile.area_m2)["biomass_c"]
    for day in range(10 * DAYS_PER_YEAR):
        tile.step_day(weather.day(day), day, rng)
    assert forest.diagnostics(tile.area_m2)["biomass_c"] > start * 3


def test_stand_profile_is_ordered_and_complete():
    forest, _, _ = run_forest(30)
    profile = forest.stand_profile()
    heights = [row["height"] for row in profile]
    assert heights == sorted(heights, reverse=True)
    for row in profile:
        assert row["crown_base"] < row["height"]
        assert row["crown_diameter"] > 0.0
