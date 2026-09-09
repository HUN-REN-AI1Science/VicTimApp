"""The 2D tiled region and its driving loop.

Milestone 1 runs `Grid(nx=1, ny=1)`. Everything here -- per-tile indexing, the
day loop over tiles, the annual dispersal pass -- is already written for the
general case, so enlarging the region is a configuration change rather than a
rewrite. `tests/test_grid.py` asserts that a 3x3 grid with `NoDispersal`
and `NoLateralShading` reproduces the 1x1 trajectory exactly, which is what makes
that claim checkable.

Two things cross a tile boundary, and both are resolved here rather than inside a
tile: seed dispersal, once a year, and neighbour shading, once a day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterator, Sequence

import numpy as np

from .dispersal import DispersalKernel, NoDispersal
from .shading import LateralShading, NoLateralShading
from .tile import Tile
from .units import DAYS_PER_YEAR, DEFAULT_TILE_SIZE_M
from .weather import WeatherSeries

__all__ = ["Grid", "SimulationResult", "run_simulation"]


@dataclass
class Grid:
    """A rectangular region of tiles."""

    nx: int = 1
    ny: int = 1
    tile_size_m: float = DEFAULT_TILE_SIZE_M
    tiles: list[Tile] = field(default_factory=list)
    dispersal: DispersalKernel = field(default_factory=NoDispersal)
    shading: LateralShading = field(default_factory=NoLateralShading)
    """How much sky each tile's neighbours take. Defaults to none, so a grid is
    N independent columns unless a kernel is asked for."""

    @classmethod
    def build(
        cls,
        nx: int,
        ny: int,
        tile_factory: Callable[[int, int], Tile],
        tile_size_m: float = DEFAULT_TILE_SIZE_M,
        dispersal: DispersalKernel | None = None,
        shading: LateralShading | None = None,
    ) -> "Grid":
        """Create a grid, calling `tile_factory(x, y)` for every cell."""
        grid = cls(
            nx=nx,
            ny=ny,
            tile_size_m=tile_size_m,
            dispersal=dispersal or NoDispersal(),
            shading=shading or NoLateralShading(),
        )
        for y in range(ny):
            for x in range(nx):
                tile = tile_factory(x, y)
                tile.x, tile.y = x, y
                tile.size_m = tile_size_m
                grid.tiles.append(tile)
        return grid

    def at(self, x: int, y: int) -> Tile | None:
        if not (0 <= x < self.nx and 0 <= y < self.ny):
            return None
        return self.tiles[y * self.nx + x]

    def __iter__(self) -> Iterator[Tile]:
        return iter(self.tiles)

    def __len__(self) -> int:
        return len(self.tiles)

    @property
    def area_m2(self) -> float:
        return len(self.tiles) * self.tile_size_m**2


@dataclass
class SimulationResult:
    """Everything a run produced, ready for the API layer to serialise."""

    days: int
    tile_series: dict[tuple[int, int], list[dict]] = field(default_factory=dict)
    """Per-tile diagnostics, one record per recorded day."""
    recorded_days: list[int] = field(default_factory=list)

    def series(self, x: int = 0, y: int = 0) -> list[dict]:
        return self.tile_series[(x, y)]

    def variable(self, name: str, x: int = 0, y: int = 0) -> list[float]:
        return [record.get(name, float("nan")) for record in self.series(x, y)]

    def snapshot(self, index: int = -1) -> list[dict]:
        """All tiles at one recorded time -- what the map view renders."""
        return [records[index] for records in self.tile_series.values()]


def run_simulation(
    grid: Grid,
    weather: WeatherSeries,
    years: int,
    record_every: int = 30,
    seed: int = 0,
    progress: Callable[[int, int], None] | None = None,
    recorder: Callable[[Tile], dict] | None = None,
) -> SimulationResult:
    """Run `grid` for `years` years of daily steps.

    `progress(done_days, total_days)` is called from inside the loop, so the API
    reports real progress rather than an estimate.

    `recorder(tile)` may return extra fields to attach to each recorded snapshot,
    which is how the API captures stand and sward profiles for the vertical
    structure view without ecocore having to know those views exist.
    """
    rng = np.random.default_rng(seed)
    total_days = years * DAYS_PER_YEAR
    result = SimulationResult(days=total_days)
    result.tile_series = {(t.x, t.y): [] for t in grid.tiles}

    for day_index in range(total_days):
        day = weather.day(day_index)
        # Neighbour shading is resolved for the whole grid before any tile steps,
        # so no tile's light depends on where it sits in the iteration order. The
        # canopy heights it reads are yesterday's -- a one-day lag on a quantity
        # that moves on annual timescales, and the price of not having to step
        # every tile twice.
        sky = grid.shading.sky_fractions(grid)
        lights = {}
        for tile in grid.tiles:
            lights[(tile.x, tile.y)] = tile.step_day(
                day, day_index, rng, sky_fraction=sky.get((tile.x, tile.y), 1.0)
            )

        if (day_index + 1) % DAYS_PER_YEAR == 0:
            # Seeds produced this year are redistributed before next year starts.
            for tile in grid.tiles:
                tile.seed_rain.reset_incoming()
            grid.dispersal.disperse(grid)

        if day_index % record_every == 0 or day_index == total_days - 1:
            result.recorded_days.append(day_index)
            for tile in grid.tiles:
                record = tile.diagnostics(lights[(tile.x, tile.y)])
                if recorder is not None:
                    record.update(recorder(tile))
                record["day"] = day_index
                record["year"] = day_index / DAYS_PER_YEAR
                result.tile_series[(tile.x, tile.y)].append(record)

        if progress is not None and day_index % 100 == 0:
            progress(day_index, total_days)

    if progress is not None:
        progress(total_days, total_days)
    return result
