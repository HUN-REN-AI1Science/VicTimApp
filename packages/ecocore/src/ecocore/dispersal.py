"""Seed exchange -- the only genuinely BETWEEN-tile flux in the model.

Light and soil couple the two vegetation models *within* a tile. Seed dispersal
is what couples tiles to each other, and therefore what makes a 2D map more than
N independent columns. It is also the documented mechanism behind woody
encroachment into grassland and behind grassland persistence at forest edges.

Milestone 1 runs a 1x1 grid with `NoDispersal`, so every tile self-seeds only.
Switching to `ExponentialKernel` is the single change that turns the vertical
slice into a spatial simulation; nothing else in the model has to move.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol

__all__ = ["SeedRain", "DispersalKernel", "NoDispersal", "ExponentialKernel"]


@dataclass
class SeedRain:
    """Seeds arriving at one tile this year, in seeds m-2 y-1, keyed by PFT.

    `incoming` is what the tile receives (external rain plus neighbours);
    `outgoing` is what its own plants produced and offered to the grid.
    """

    incoming: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    outgoing: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    external: dict[str, float] = field(default_factory=dict)
    """Constant background seed rain from outside the simulated region."""

    def offer(self, pft: str, seeds_per_m2: float) -> None:
        self.outgoing[pft] = self.outgoing.get(pft, 0.0) + seeds_per_m2

    def available(self, pft: str) -> float:
        return self.incoming.get(pft, 0.0) + self.external.get(pft, 0.0)

    def reset_incoming(self) -> None:
        self.incoming = defaultdict(float)

    def reset_outgoing(self) -> None:
        self.outgoing = defaultdict(float)


class DispersalKernel(Protocol):
    """Redistributes each tile's outgoing seeds across the grid."""

    def disperse(self, grid) -> None: ...


class NoDispersal:
    """Every tile keeps its own seeds. The milestone-1 default.

    With a 1x1 grid this is exactly equivalent to any kernel, which is why the
    grid-readiness test can compare 1x1 and 3x3 runs for identical trajectories.
    """

    name = "none"

    def disperse(self, grid) -> None:
        for tile in grid.tiles:
            for pft, amount in tile.seed_rain.outgoing.items():
                tile.seed_rain.incoming[pft] += amount
            tile.seed_rain.reset_outgoing()


@dataclass
class ExponentialKernel:
    """Negative-exponential dispersal, the standard form for tree seed shadows.

    Weight of a source tile at distance d is exp(-d / mean_distance_m), including
    d = 0 (self-seeding), normalised over the neighbourhood so seeds are
    conserved. Seeds leaving the grid edge are lost, which is the honest
    behaviour for a finite region.
    """

    mean_distance_m: float = 30.0
    radius_tiles: int = 2
    name: str = "exponential"

    def disperse(self, grid) -> None:
        cell = grid.tile_size_m
        offsets: list[tuple[int, int, float]] = []
        for dx in range(-self.radius_tiles, self.radius_tiles + 1):
            for dy in range(-self.radius_tiles, self.radius_tiles + 1):
                distance = math.hypot(dx, dy) * cell
                offsets.append((dx, dy, math.exp(-distance / self.mean_distance_m)))
        total_weight = sum(w for _, _, w in offsets)

        for tile in grid.tiles:
            for pft, amount in tile.seed_rain.outgoing.items():
                for dx, dy, weight in offsets:
                    target = grid.at(tile.x + dx, tile.y + dy)
                    if target is None:
                        continue  # dispersed out of the region and lost
                    target.seed_rain.incoming[pft] += amount * weight / total_weight
            tile.seed_rain.reset_outgoing()
