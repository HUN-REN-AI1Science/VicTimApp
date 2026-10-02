"""The driving loop: steps one tile through a run and records its history.

A tile self-seeds -- whatever it offered this year is what it receives next
year, none of it lost and none of it borrowed from elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .tile import Tile
from .units import DAYS_PER_YEAR
from .weather import WeatherSeries

__all__ = ["SimulationResult", "run_simulation"]


@dataclass
class SimulationResult:
    """Everything a run produced, ready for the API layer to serialise."""

    days: int
    series: list[dict] = field(default_factory=list)
    """Diagnostics, one record per recorded day."""
    recorded_days: list[int] = field(default_factory=list)

    def variable(self, name: str) -> list[float]:
        return [record.get(name, float("nan")) for record in self.series]


def run_simulation(
    tile: Tile,
    weather: WeatherSeries,
    years: int,
    record_every: int = 30,
    seed: int = 0,
    progress: Callable[[int, int], None] | None = None,
    recorder: Callable[[Tile], dict] | None = None,
) -> SimulationResult:
    """Run `tile` for `years` years of daily steps.

    `progress(done_days, total_days)` is called from inside the loop, so the API
    reports real progress rather than an estimate.

    `recorder(tile)` may return extra fields to attach to each recorded snapshot,
    which is how the API captures stand and sward profiles for the vertical
    structure view without ecocore having to know those views exist.
    """
    rng = np.random.default_rng(seed)
    total_days = years * DAYS_PER_YEAR
    result = SimulationResult(days=total_days)

    for day_index in range(total_days):
        day = weather.day(day_index)
        light = tile.step_day(day, day_index, rng)

        if (day_index + 1) % DAYS_PER_YEAR == 0:
            # Seeds produced this year are what the tile receives next year.
            tile.seed_rain.reset_incoming()
            for pft, amount in tile.seed_rain.outgoing.items():
                tile.seed_rain.incoming[pft] += amount
            tile.seed_rain.reset_outgoing()

        if day_index % record_every == 0 or day_index == total_days - 1:
            record = tile.diagnostics(light)
            if recorder is not None:
                record.update(recorder(tile))
            record["day"] = day_index
            record["year"] = day_index / DAYS_PER_YEAR
            result.recorded_days.append(day_index)
            result.series.append(record)

        if progress is not None and day_index % 100 == 0:
            progress(day_index, total_days)

    if progress is not None:
        progress(total_days, total_days)
    return result
