"""Tile-level disturbances, broadcast to every vegetation module.

Light and soil couple the models through resources. Disturbance is the third
channel, and it needs its own mechanism because it is not a resource: when a
mower crosses a tile it removes grass AND it destroys tree saplings, and a model
in which mowing touched only the grass would predict that hay meadows turn into
woodland -- which is the opposite of what they do.

Emission and response are separated into two phases by `Tile.step_day` so that no
module has to run before another for the coupling to work.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Defoliation"]


@dataclass(frozen=True)
class Defoliation:
    """Biomass removed above a cutting or browsing height."""

    source: str
    """`"mowing"` or `"grazing"`. Diagnostics only."""

    cut_height_m: float
    """Everything above this height is removed from herbaceous plants."""

    removal_fraction: float = 0.9
    """Share of removed CARBON exported from the tile; the rest becomes litter."""

    nitrogen_removal_fraction: float | None = None
    """Share of removed NITROGEN exported. Defaults to `removal_fraction`.

    Carbon and nitrogen do not leave together when an animal is the agent: a
    grazer respires most of the carbon it eats but excretes most of the nitrogen,
    so dung and urine return a far larger share of the nitrogen than of the
    carbon. Hay carted off a meadow does take both, which is why this defaults to
    `removal_fraction` and only grazing overrides it.
    """

    @property
    def n_removal_fraction(self) -> float:
        """`nitrogen_removal_fraction`, falling back to `removal_fraction`."""
        if self.nitrogen_removal_fraction is None:
            return self.removal_fraction
        return self.nitrogen_removal_fraction

    woody_kill_height_m: float = 0.0
    """Woody individuals shorter than this are destroyed outright.

    A mower does not merely trim a tree sapling, it cuts it off at the base; a
    grazing animal browses it out. This is the parameter that decides whether a
    managed tile can be invaded by trees at all.
    """

    woody_kill_fraction: float = 1.0
    """Share of the woody individuals below `woody_kill_height_m` that die."""
