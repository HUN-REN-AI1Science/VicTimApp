"""Lateral shading -- what a tile's NEIGHBOURS take out of its sky.

Light and soil couple the two vegetation models *within* a tile; seed dispersal
couples tiles to each other once a year. This module is the second between-tile
flux and the daily one: a tile standing next to a 30 m canopy does not receive
the open-sky irradiance, however empty its own light profile is.

The one-profile-and-one-column-per-tile invariant is untouched. Nothing here
resolves light: a kernel returns one scalar per tile, the fraction of open-sky
irradiance that reaches the top of that tile's own canopy, and `Tile.step_day`
scales its incident PAR by it before the single shared profile is resolved. The
per-tile identity `sum(absorbed) + floor == incident` therefore still holds
exactly, with `incident` now being what the tile actually receives. What changes
is the grid-level statement: a shaded region absorbs LESS than the open-sky flux
over its area, never more.

Method (sky view factor from horizon angles; Steyn 1980, "The calculation of view
factors from fisheye-lens photographs", Atmos.-Ocean 18; Oke, *Boundary Layer
Climates*, 2nd ed., ch. 8):

    theta_i = max over tiles along azimuth sector i of atan(h_neighbour / d)
    SVF     = 1 - (1/N) * sum_i sin^2(theta_i)

with N azimuth sectors and d the centre-to-centre horizontal distance. A tile
with an unobstructed horizon has SVF = 1; one walled in by infinitely tall
neighbours has SVF = 0.

Simplifications, all of which make this a first-order treatment rather than a
radiation model:

  * Sun position is not modelled, so all radiation is treated as diffuse and
    isotropic. A real stand loses far more light to a neighbour at a low solar
    elevation in the morning than at noon; this returns the day-mean effect.
  * Distance is centre-to-centre, so the shading by an immediately adjacent tile
    is understated -- its crown edge is half a tile nearer than its centre. The
    alternative, edge-to-edge, overstates it by the same argument. Centre to
    centre is the conservative choice.
  * Tiles beyond the grid edge count as open sky, which is the same honest
    treatment of a finite region that `dispersal.ExponentialKernel` gives seeds
    that leave it.

`NoLateralShading` is the default everywhere, so enlarging a grid still
reproduces N independent columns unless a kernel is asked for -- which is what
keeps `tests/test_grid.py::test_grid_of_nine_reproduces_a_single_tile` a
meaningful regression guard.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

__all__ = ["LateralShading", "NoLateralShading", "SkyViewShading"]


class LateralShading(Protocol):
    """Computes each tile's sky view factor from its neighbours' canopy heights."""

    name: str

    def sky_fractions(self, grid) -> dict[tuple[int, int], float]:
        """Fraction of open-sky irradiance reaching each tile, keyed by (x, y)."""
        ...


class NoLateralShading:
    """Every tile sees the whole sky. The default.

    With this in place a grid is exactly N independent columns, which is what
    makes a multi-tile run comparable to a 1x1 run.
    """

    name = "none"

    def sky_fractions(self, grid) -> dict[tuple[int, int], float]:
        return {(tile.x, tile.y): 1.0 for tile in grid.tiles}


@dataclass
class SkyViewShading:
    """Horizon-angle sky view factor over a square neighbourhood.

    Args:
        radius_tiles: how far to look for a horizon. Two tiles is enough at the
            default 20 m tile size: a 40 m canopy two tiles away subtends 45
            degrees, three tiles away 34 degrees, and sin^2 falls off fast.
        n_sectors: azimuth sectors the hemisphere is divided into. Eight is the
            Moore neighbourhood's own resolution -- finer sectors would claim a
            directional precision the tile grid does not have.
    """

    radius_tiles: int = 2
    n_sectors: int = 8
    name: str = "sky_view"

    _offsets: list[tuple[int, int, float, int]] = field(
        default_factory=list, init=False, repr=False, compare=False
    )
    _offsets_cell: float | None = field(default=None, init=False, repr=False, compare=False)

    def _neighbourhood(self, cell: float) -> list[tuple[int, int, float, int]]:
        """`(dx, dy, distance_m, sector)` for every neighbour, cached per cell size.

        Geometry does not change while a run proceeds, and this is called once
        per simulated day, so the offsets are built once.
        """
        if self._offsets_cell == cell:
            return self._offsets

        offsets: list[tuple[int, int, float, int]] = []
        for dx in range(-self.radius_tiles, self.radius_tiles + 1):
            for dy in range(-self.radius_tiles, self.radius_tiles + 1):
                if dx == 0 and dy == 0:
                    continue  # a tile does not shade itself; its own profile does that
                azimuth = math.atan2(dy, dx) % (2.0 * math.pi)
                sector = int(azimuth / (2.0 * math.pi) * self.n_sectors) % self.n_sectors
                offsets.append((dx, dy, math.hypot(dx, dy) * cell, sector))

        self._offsets = offsets
        self._offsets_cell = cell
        return offsets

    def sky_fractions(self, grid) -> dict[tuple[int, int], float]:
        offsets = self._neighbourhood(grid.tile_size_m)
        out: dict[tuple[int, int], float] = {}

        for tile in grid.tiles:
            # Highest horizon angle seen in each sector; an empty sector, and any
            # sector pointing off the grid edge, stays at open sky.
            horizon = [0.0] * self.n_sectors
            for dx, dy, distance, sector in offsets:
                neighbour = grid.at(tile.x + dx, tile.y + dy)
                if neighbour is None:
                    continue
                height = neighbour.canopy_top_m
                if height <= 0.0:
                    continue
                angle = math.atan2(height, distance)
                if angle > horizon[sector]:
                    horizon[sector] = angle

            blocked = sum(math.sin(angle) ** 2 for angle in horizon) / self.n_sectors
            out[(tile.x, tile.y)] = max(0.0, 1.0 - blocked)

        return out
