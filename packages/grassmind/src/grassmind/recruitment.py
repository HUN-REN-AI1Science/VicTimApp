"""Herbaceous establishment.

Grassland regenerates from a large seed bank into whatever gaps the sward and the
tree canopy leave. As in `formind.recruitment`, the light gate reads the shared
floor irradiance, so tree shading suppresses grass recruitment with no explicit
forest-to-grassland channel in the code.
"""

from __future__ import annotations

__all__ = ["establishment_number", "ESTABLISHMENT_EFFICIENCY"]

ESTABLISHMENT_EFFICIENCY = 0.15
"""Share of arriving seeds that become established plants under ideal light.

Lumps germination, seedling survival and -- importantly -- clonal tillering,
which in a real sward contributes more new individuals than seed does. Calibrated
so an unshaded sward equilibrates at a few thousand tillers per m2 against the
PFTs' background mortality.
"""


def establishment_number(
    seeds_per_m2: float,
    floor_light_fraction: float,
    tile_area_m2: float,
    current_density_per_m2: float,
    p,
) -> float:
    """Number of new plants established in a tile this year."""
    if seeds_per_m2 <= 0.0 or floor_light_fraction < p.establishment_light_fraction:
        return 0.0
    headroom = (floor_light_fraction - p.establishment_light_fraction) / max(
        1e-9, 1.0 - p.establishment_light_fraction
    )
    space = max(0.0, 1.0 - current_density_per_m2 / p.max_density_per_m2)
    return seeds_per_m2 * tile_area_m2 * min(1.0, headroom) * space * ESTABLISHMENT_EFFICIENCY
