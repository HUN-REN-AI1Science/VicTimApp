"""The driving loop: progress reporting, daily/annual stepping, self-seeding."""

import pytest
from ecocore import SoilColumn, SoilParameters, Tile, run_simulation, synthetic_weather
from ecocore.cohort import CanopyElement


class StubModule:
    """A minimal VegetationModule: fixed canopy, counts the days it was stepped."""

    name = "stub"

    def __init__(self, leaf_area=400.0):
        self.leaf_area = leaf_area
        self.days = 0
        self.years = 0

    def canopy_elements(self):
        return [
            CanopyElement(key=id(self), base_m=0.0, top_m=2.0, leaf_area_m2=self.leaf_area, k=0.6)
        ]

    def water_demand_mm(self, day, light):
        return 1.0

    def step_day(self, ctx):
        self.days += 1

    def step_year(self, ctx):
        self.years += 1
        ctx.seed_rain.offer("stub", 10.0)

    def diagnostics(self, area_m2):
        return {"days": self.days, "years": self.years, "leaf_area": self.leaf_area / area_m2}


def build_tile():
    return Tile(soil=SoilColumn(SoilParameters()), modules=[StubModule()])


def test_progress_is_reported_from_inside_the_loop():
    calls = []
    run_simulation(
        build_tile(),
        synthetic_weather(1, seed=2),
        years=2,
        record_every=365,
        progress=lambda done, total: calls.append((done, total)),
    )
    assert calls[0][0] == 0
    assert calls[-1] == (730, 730)
    assert len(calls) > 2


def test_modules_are_stepped_daily_and_annually():
    tile = build_tile()
    run_simulation(tile, synthetic_weather(1, seed=1), years=3, record_every=365)
    module = tile.modules[0]
    assert module.days == 3 * 365
    assert module.years == 3


def test_results_expose_a_series():
    result = run_simulation(build_tile(), synthetic_weather(1, seed=1), years=1, record_every=180)
    assert len(result.series) == len(result.recorded_days)
    assert len(result.variable("soil_c")) == len(result.recorded_days)


def test_a_tile_receives_next_year_what_it_offered_this_year():
    """Self-seeding: nothing lost, nothing borrowed -- `NoDispersal`'s old behaviour."""
    tile = build_tile()
    run_simulation(tile, synthetic_weather(1, seed=1), years=2, record_every=365)
    # The stub offers 10.0 "stub" seeds every year-end; with no dispersal kernel
    # left in the model, a tile is the only source of its own incoming seeds.
    assert tile.seed_rain.incoming["stub"] == pytest.approx(10.0)
