"""Tree death.

FORMIND combines four sources (Handbook, "Mortality"):

  * background mortality, constant per PFT;
  * size-dependent mortality, elevated for small trees;
  * growth-dependent mortality, elevated for trees whose diameter increment has
    collapsed -- this is how suppressed understorey trees eventually die, and it
    is the mechanism that converts shading by neighbours into demography;
  * space limitation, when crowns no longer fit.

Space limitation is evaluated PER HEIGHT LAYER, not over the whole patch. That
distinction matters: a global crown-area limit forbids a tall tree and a short
tree from occupying the same ground, which pins stand LAI near a single crown's
LAI and leaves an implausibly bright forest floor. Layer-wise limiting lets
canopies stack, which is what produces realistic multi-layered stands.

Rates are annual and applied in `step_year`.
"""

from __future__ import annotations

import math

from ecocore.units import LAYER_HEIGHT_M

__all__ = ["annual_mortality_rate", "layer_range", "layered_space_limitation"]


def annual_mortality_rate(dbh: float, annual_increment: float, p) -> float:
    """Probability that a given tree dies during one year, in [0, 1]."""
    rate = p.background_mortality

    # Small trees are more vulnerable; the effect decays over dbh_mortality_scale.
    if p.dbh_mortality_scale > 0.0:
        rate += p.background_mortality * 2.0 * math.exp(-dbh / p.dbh_mortality_scale)

    # Suppressed trees: increment below threshold ramps mortality up linearly.
    if annual_increment < p.growth_mortality_threshold:
        shortfall = 1.0 - annual_increment / max(p.growth_mortality_threshold, 1e-12)
        rate += p.growth_mortality_max * max(0.0, min(1.0, shortfall))

    return max(0.0, min(1.0, rate))


def layer_range(crown_base_m: float, height_m: float) -> tuple[int, int]:
    """Inclusive index range of light layers a crown occupies."""
    lo = max(0, int(crown_base_m // LAYER_HEIGHT_M))
    hi = max(lo, int(math.ceil(height_m / LAYER_HEIGHT_M)) - 1)
    return lo, hi


def layered_space_limitation(
    members: list[tuple[object, float, float, int, int]],
    tile_area_m2: float,
) -> dict[object, float]:
    """Decide how many individuals must die because their layer is overfull.

    Args:
        members: `(key, n_individuals, crown_area_m2, layer_lo, layer_hi)` per cohort.
        tile_area_m2: ground area available in each layer.

    Returns:
        `{key: number of individuals to remove}`. Smallest trees are removed
        first within an overfull layer -- FORMIND's self-thinning rule, in which
        the canopy closes and the understorey pays.
    """
    if not members or tile_area_m2 <= 0.0:
        return {}

    counts = {key: n for key, n, _, _, _ in members}
    removals: dict[object, float] = {}

    max_layer = max(hi for _, _, _, _, hi in members)
    for layer in range(max_layer, -1, -1):
        present = [m for m in members if m[3] <= layer <= m[4] and counts[m[0]] > 0.0]
        if not present:
            continue
        occupied = sum(crown * counts[key] for key, _, crown, _, _ in present)
        excess = occupied - tile_area_m2
        if excess <= 0.0:
            continue
        for key, _n, crown, _, _ in sorted(present, key=lambda m: m[2]):
            if excess <= 0.0:
                break
            if crown <= 0.0:
                continue
            removable = min(counts[key], excess / crown)
            if removable <= 0.0:
                continue
            counts[key] -= removable
            removals[key] = removals.get(key, 0.0) + removable
            excess -= removable * crown

    return removals
