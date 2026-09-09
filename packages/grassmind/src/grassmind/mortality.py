"""Herbaceous mortality.

Two sources dominate in a managed sward:

  * background turnover, which is fast -- an appreciable fraction of a grassland
    community is replaced every year;
  * shade mortality, which is the process that lets an advancing tree canopy
    actually remove grassland rather than merely slow it. The light fraction that
    drives it is the irradiance at the plant's OWN leaves, taken from the shared
    profile, so tree shading and neighbour shading act through one number.
"""

from __future__ import annotations

__all__ = ["annual_mortality_rate", "density_excess_fraction"]


def annual_mortality_rate(light_fraction: float, p) -> float:
    """Annual probability of death for one plant, in [0, 1]."""
    rate = p.background_mortality
    if light_fraction < p.shade_mortality_light_fraction:
        shortfall = 1.0 - light_fraction / max(p.shade_mortality_light_fraction, 1e-12)
        rate += p.shade_mortality_max * max(0.0, min(1.0, shortfall))
    return max(0.0, min(1.0, rate))


def density_excess_fraction(density_per_m2: float, p) -> float:
    """Fraction of plants that must die because the sward is over-dense."""
    if density_per_m2 <= p.max_density_per_m2:
        return 0.0
    return min(1.0, (density_per_m2 - p.max_density_per_m2) / density_per_m2)
