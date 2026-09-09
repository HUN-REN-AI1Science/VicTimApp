"""Grid and dispersal tests.

`test_grid_of_nine_reproduces_a_single_tile` is the grid-readiness check: it is
what makes the claim "milestone 1 is a 1x1 grid, but the code is already the 2D
code" verifiable rather than aspirational.
"""

import numpy as np
import pytest

from ecocore import (
    ExponentialKernel,
    Grid,
    NoDispersal,
    SoilColumn,
    SoilParameters,
    Tile,
    run_simulation,
    synthetic_weather,
)


class StubModule:
    """A minimal VegetationModule: fixed canopy, counts the days it was stepped."""

    name = "stub"

    def __init__(self, leaf_area=400.0):
        self.leaf_area = leaf_area
        self.days = 0
        self.years = 0

    def canopy_elements(self):
        from ecocore.cohort import CanopyElement

        return [CanopyElement(key=id(self), base_m=0.0, top_m=2.0,
                              leaf_area_m2=self.leaf_area, k=0.6)]

    def water_demand_mm(self, day, light):
        return 1.0

    def step_day(self, ctx):
        self.days += 1

    def step_year(self, ctx):
        self.years += 1
        ctx.seed_rain.offer("stub", 10.0)

    def diagnostics(self, area_m2):
        return {"days": self.days, "years": self.years, "leaf_area": self.leaf_area / area_m2}


def build_grid(nx, ny, dispersal=None):
    def factory(x, y):
        return Tile(soil=SoilColumn(SoilParameters()), modules=[StubModule()])

    return Grid.build(nx, ny, factory, dispersal=dispersal or NoDispersal())


def test_grid_indexing_and_bounds():
    grid = build_grid(3, 2)
    assert len(grid) == 6
    assert grid.at(2, 1).x == 2 and grid.at(2, 1).y == 1
    assert grid.at(3, 0) is None
    assert grid.at(-1, 0) is None


def test_grid_of_nine_reproduces_a_single_tile():
    """Nine independent tiles must each trace the 1x1 trajectory exactly.

    This is what proves the vertical slice generalises: if enlarging the grid
    changed a tile's result while dispersal is off, some state would be leaking
    between tiles.
    """
    weather = synthetic_weather(3, seed=7)
    one = run_simulation(build_grid(1, 1), weather, years=4, record_every=90, seed=7)
    nine = run_simulation(build_grid(3, 3), weather, years=4, record_every=90, seed=7)

    reference = one.series(0, 0)
    for x in range(3):
        for y in range(3):
            series = nine.series(x, y)
            assert len(series) == len(reference)
            for a, b in zip(reference, series):
                assert a["stub_days"] == b["stub_days"]
                assert a["soil_c"] == pytest.approx(b["soil_c"], rel=1e-12)
                assert a["soil_water_mm"] == pytest.approx(b["soil_water_mm"], rel=1e-12)


def test_no_dispersal_keeps_seeds_at_home():
    grid = build_grid(2, 2)
    grid.tiles[0].seed_rain.offer("oak", 5.0)
    NoDispersal().disperse(grid)
    assert grid.tiles[0].seed_rain.incoming["oak"] == pytest.approx(5.0)
    assert grid.tiles[1].seed_rain.incoming.get("oak", 0.0) == 0.0


def test_exponential_kernel_spreads_seeds_to_neighbours():
    grid = build_grid(5, 5, ExponentialKernel(mean_distance_m=30.0, radius_tiles=2))
    centre = grid.at(2, 2)
    centre.seed_rain.offer("oak", 100.0)
    grid.dispersal.disperse(grid)
    assert centre.seed_rain.incoming["oak"] > 0.0
    assert grid.at(3, 2).seed_rain.incoming["oak"] > 0.0
    # Closer neighbours must receive more than distant ones.
    assert grid.at(3, 2).seed_rain.incoming["oak"] > grid.at(4, 2).seed_rain.incoming["oak"]


def test_exponential_kernel_conserves_seeds_away_from_the_edge():
    grid = build_grid(9, 9, ExponentialKernel(mean_distance_m=25.0, radius_tiles=2))
    grid.at(4, 4).seed_rain.offer("oak", 100.0)
    grid.dispersal.disperse(grid)
    total = sum(t.seed_rain.incoming.get("oak", 0.0) for t in grid.tiles)
    assert total == pytest.approx(100.0, rel=1e-9)


def test_seeds_dispersed_off_the_edge_are_lost():
    grid = build_grid(1, 1, ExponentialKernel(mean_distance_m=40.0, radius_tiles=2))
    grid.at(0, 0).seed_rain.offer("oak", 100.0)
    grid.dispersal.disperse(grid)
    assert grid.at(0, 0).seed_rain.incoming["oak"] < 100.0


def test_progress_is_reported_from_inside_the_loop():
    calls = []
    run_simulation(
        build_grid(1, 1),
        synthetic_weather(1, seed=2),
        years=2,
        record_every=365,
        progress=lambda done, total: calls.append((done, total)),
    )
    assert calls[0][0] == 0
    assert calls[-1] == (730, 730)
    assert len(calls) > 2


def test_modules_are_stepped_daily_and_annually():
    grid = build_grid(1, 1)
    run_simulation(grid, synthetic_weather(1, seed=1), years=3, record_every=365)
    module = grid.at(0, 0).modules[0]
    assert module.days == 3 * 365
    assert module.years == 3


def test_results_expose_series_and_snapshots():
    result = run_simulation(build_grid(2, 2), synthetic_weather(1, seed=1), years=1, record_every=180)
    assert len(result.snapshot(-1)) == 4
    assert len(result.variable("soil_c", 0, 0)) == len(result.recorded_days)
