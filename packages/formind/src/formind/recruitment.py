"""Seedling establishment and the sub-breast-height seedling bank.

A tree's diameter at breast height is not defined until the tree reaches breast
height, so a gap model cannot represent a 30 cm seedling as a very thin tree: the
diameter allometry, fitted on mature stems, then predicts that a seedling is
several metres tall and grows metres per season. Modelling seedlings as thin
trees makes tree invasion of grassland unstoppable and mowing irrelevant, which
is the opposite of what managed meadows do.

So seedlings live in their own bank, tracked by HEIGHT rather than diameter, and
are promoted into the tree cohort list only when they reach breast height. The
years they spend in the bank are the real regeneration bottleneck: it is where
shading by the grass sward acts, and where a mower or a grazing animal removes
them.

Light gates every stage, and the light comes from `ecocore.light`, already
attenuated by BOTH the tree canopy and the grass sward. That is why this port
needs no explicit "grass suppresses tree seedlings" channel -- the suppression is
already mechanistic.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "BREAST_HEIGHT_M",
    "SeedlingCohort",
    "establishment_number",
    "seedling_height_growth",
    "seedling_mortality_rate",
]

BREAST_HEIGHT_M = 1.3
"""Height at which a seedling becomes a measurable tree and leaves the bank."""


@dataclass
class SeedlingCohort:
    """A group of identical sub-breast-height seedlings."""

    pft: str
    n: float
    height_m: float
    age_years: int = 0


def establishment_number(
    seeds_per_m2: float,
    floor_light_fraction: float,
    tile_area_m2: float,
    free_ground_fraction: float,
    p,
) -> float:
    """Number of new seedlings entering the bank this year."""
    if seeds_per_m2 <= 0.0:
        return 0.0
    if floor_light_fraction < p.establishment_light_fraction:
        return 0.0
    headroom = (floor_light_fraction - p.establishment_light_fraction) / max(
        1e-9, 1.0 - p.establishment_light_fraction
    )
    success = min(1.0, headroom) * max(0.0, min(1.0, free_ground_fraction))
    return seeds_per_m2 * tile_area_m2 * success


def seedling_height_growth(light_fraction: float, p) -> float:
    """Annual height increment of a seedling (m y-1).

    Saturating in light, so a shaded seedling creeps upward and a seedling in a
    gap races for breast height.
    """
    if light_fraction <= 0.0:
        return 0.0
    response = light_fraction / (light_fraction + p.seedling_light_half_saturation)
    return p.seedling_growth_max * response


def seedling_mortality_rate(light_fraction: float, p) -> float:
    """Annual probability that a seedling dies, in [0, 1].

    Baseline seedling mortality is high even in good light; below the PFT's
    establishment threshold it rises steeply, which is what removes the seedling
    bank once a canopy -- of trees or of grass -- closes over it.
    """
    rate = p.seedling_mortality
    if light_fraction < p.establishment_light_fraction:
        shortfall = 1.0 - light_fraction / max(p.establishment_light_fraction, 1e-12)
        rate += (1.0 - p.seedling_mortality) * max(0.0, min(1.0, shortfall))
    return max(0.0, min(1.0, rate))
