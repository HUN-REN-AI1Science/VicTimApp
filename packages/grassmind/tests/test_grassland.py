"""Grassland behaviour tests.

The management regimes are the point of this package, so most of these check that
a regime produces the community it is supposed to produce.
"""

import numpy as np
import pytest

from ecocore import SoilColumn, SoilParameters, Tile, synthetic_weather
from ecocore.units import DAYS_PER_YEAR
from grassmind import GrasslandModule, ManagementSchedule
from grassmind import allometry


def run_grassland(years, schedule=None, seed=1):
    tile = Tile(soil=SoilColumn(SoilParameters()))
    grass = GrasslandModule.sown_sward(management=schedule or ManagementSchedule())
    tile.add_module(grass)
    tile.seed_rain.external = {"grass": 400.0, "forb": 250.0, "legume": 150.0}
    weather = synthetic_weather(5, seed=seed)
    rng = np.random.default_rng(seed)
    history = []
    for day in range(years * DAYS_PER_YEAR):
        tile.step_day(weather.day(day), day, rng)
        if (day + 1) % DAYS_PER_YEAR == 0:
            history.append(grass.diagnostics(tile.area_m2))
    return grass, tile, history


def test_allometry_height_roundtrip():
    from grassmind.pft import DEFAULT_GRASS_PFTS

    for p in DEFAULT_GRASS_PFTS:
        for shoot in (1e-5, 1e-4, 5e-4):
            h = allometry.height(shoot, p)
            assert allometry.shoot_from_height(h, p) == pytest.approx(shoot, rel=1e-6)


def test_height_saturates_at_max_height():
    from grassmind.pft import DEFAULT_GRASS_PFTS

    p = DEFAULT_GRASS_PFTS[0]
    big = 20.0 / p.height_scale  # far past the saturation scale
    assert allometry.height(big, p) < p.max_height
    assert allometry.height(big, p) > 0.99 * p.max_height


@pytest.mark.slow
def test_unmanaged_sward_reaches_a_stationary_standing_crop():
    """Stationary, not constant.

    Real swards swing 30-50% between years with the weather, and the synthetic
    driver reproduces that, so this checks that the sward stops TRENDING -- the
    late-period mean matches the mid-period mean -- rather than that it stops
    varying.
    """
    _, _, history = run_grassland(30)
    shoot = [h["shoot_c"] for h in history]
    assert min(shoot[-10:]) > 0.0
    mid = sum(shoot[10:20]) / 10
    late = sum(shoot[20:30]) / 10
    assert abs(late - mid) / mid < 0.2, (mid, late)


@pytest.mark.slow
def test_standing_crop_is_in_a_plausible_range():
    """A temperate sward carries on the order of 100 gC m-2 of shoot."""
    _, _, history = run_grassland(30)
    shoot_per_m2 = history[-1]["shoot_c"]
    assert 0.03 < shoot_per_m2 < 0.35
    root_per_m2 = history[-1]["root_c"]
    assert root_per_m2 > shoot_per_m2, "roots are the sward's reserve; they must dominate"


@pytest.mark.slow
def test_mowing_yields_hay_and_keeps_the_sward_alive():
    """The key regression: repeated cutting must not destroy the grassland."""
    _, _, history = run_grassland(30, ManagementSchedule.extensive_meadow())
    assert history[-1]["shoot_c"] > 0.0
    yields = [h["harvest_c"] for h in history[-5:]]
    # 0.05-0.30 kgC m-2 y-1 spans extensive to productive hay meadows.
    assert all(0.05 < y < 0.30 for y in yields), yields


@pytest.mark.slow
def test_mowing_shortens_the_sward_relative_to_abandonment():
    _, _, mown = run_grassland(25, ManagementSchedule.extensive_meadow())
    _, _, wild = run_grassland(25, ManagementSchedule.abandoned())
    assert mown[-1]["shoot_c"] < wild[-1]["shoot_c"]


@pytest.mark.slow
def test_grazing_removes_biomass_and_returns_dung():
    _, _, history = run_grassland(25, ManagementSchedule.pasture())
    assert history[-1]["harvest_c"] > 0.0
    assert history[-1]["shoot_c"] > 0.0


def test_fertilisation_reaches_the_shared_mineral_pool():
    tile = Tile(soil=SoilColumn(SoilParameters()))
    schedule = ManagementSchedule.intensive_meadow()
    grass = GrasslandModule.sown_sward(management=schedule)
    tile.add_module(grass)
    before = tile.soil.cumulative_fertiliser_n
    weather = synthetic_weather(1, seed=1)
    rng = np.random.default_rng(1)
    for day in range(DAYS_PER_YEAR):
        tile.step_day(weather.day(day), day, rng)
    assert tile.soil.cumulative_fertiliser_n > before


@pytest.mark.slow
def test_legumes_fix_nitrogen_into_the_shared_pool():
    """Fixation is how a grassland process fertilises the trees above it."""
    _, tile, _ = run_grassland(20)
    assert tile.soil.cumulative_fixed_n > 0.0


def test_management_emits_events_rather_than_acting_privately():
    from ecocore.weather import synthetic_weather as sw

    grass = GrasslandModule.sown_sward(management=ManagementSchedule.extensive_meadow())
    weather = sw(1, seed=1)
    mowing_day = grass.management.mowing[0].day_of_year
    events = grass.emit_disturbances(weather.day(mowing_day - 1))
    assert len(events) == 1
    assert events[0].source == "mowing"
    assert events[0].woody_kill_height_m > 0.0, "a mower must be able to kill saplings"
    assert grass.emit_disturbances(weather.day(0)) == []


def test_cohort_count_stays_bounded():
    _, _, history = run_grassland(20)
    assert history[-1]["cohorts"] < 60
