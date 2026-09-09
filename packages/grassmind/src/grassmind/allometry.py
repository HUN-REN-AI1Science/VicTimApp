"""Herbaceous plant geometry from shoot biomass.

Where FORMIND drives everything from stem diameter, GRASSMIND drives everything
from shoot carbon: grasses have no stem allometry worth the name, so height and
leaf area are saturating functions of accumulated shoot mass.

The shared light module does not care about this difference -- both models hand
it `CanopyElement`s -- which is exactly what makes the two portable into one
canopy.
"""

from __future__ import annotations

import math

__all__ = ["height", "leaf_area", "ground_area", "shoot_from_height"]


def height(shoot_c: float, p) -> float:
    """Saturating height-mass relation, H = h_max * (1 - exp(-a * shoot)) (m)."""
    if shoot_c <= 0.0:
        return 0.0
    return p.max_height * (1.0 - math.exp(-p.height_scale * shoot_c))


def leaf_area(shoot_c: float, p) -> float:
    """One-sided leaf area of one plant (m2), via specific leaf area."""
    return max(0.0, shoot_c) * p.leaf_fraction_of_shoot * p.specific_leaf_area


def ground_area(shoot_c: float, p) -> float:
    """Ground area one plant occupies (m2).

    Derived from leaf area and the plant's internal leaf area index, so that
    self-shading within a tussock is represented the same way a tree crown's is.
    """
    if p.plant_lai <= 0.0:
        return 0.0
    return leaf_area(shoot_c, p) / p.plant_lai


def shoot_from_height(h: float, p) -> float:
    """Invert `height`. Used by mowing to work out how much biomass a cut removes."""
    if h <= 0.0:
        return 0.0
    ratio = max(1e-9, 1.0 - min(h, p.max_height * 0.999) / p.max_height)
    return -math.log(ratio) / p.height_scale
