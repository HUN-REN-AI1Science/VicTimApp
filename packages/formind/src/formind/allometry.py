"""Tree geometry from stem diameter.

FORMIND is a diameter-driven model: a tree's state is its DBH, and height, crown
size, leaf area and biomass are all derived from it through power-law allometries
fitted per plant functional type (FORMIND Handbook, "Tree geometry"). Growth
therefore means converting a carbon increment into a diameter increment, which is
what `diameter_increment` does.

All lengths are metres, all masses kgC per individual.
"""

from __future__ import annotations

import math

from ecocore.units import KG_C_PER_KG_ODM

__all__ = [
    "height",
    "crown_diameter",
    "crown_area",
    "crown_base",
    "leaf_area",
    "aboveground_biomass_c",
    "diameter_increment",
    "diameter_from_biomass",
]


def height(dbh: float, p) -> float:
    """H = h0 * D^h1 (m)."""
    return p.h0 * max(dbh, 0.0) ** p.h1


def crown_diameter(dbh: float, p) -> float:
    """CD = cd0 * D^cd1 (m)."""
    return p.cd0 * max(dbh, 0.0) ** p.cd1


def crown_area(dbh: float, p) -> float:
    """Ground area covered by one crown (m2)."""
    return math.pi * 0.25 * crown_diameter(dbh, p) ** 2


def crown_base(dbh: float, p) -> float:
    """Height of the bottom of the crown (m)."""
    return height(dbh, p) * (1.0 - p.crown_length_fraction)


def leaf_area(dbh: float, p) -> float:
    """One-sided leaf area of a single tree (m2).

    Expressed as crown ground area times the leaf area index held *within* the
    crown, so crown geometry and light interception cannot disagree.
    """
    return crown_area(dbh, p) * p.crown_lai


def aboveground_biomass_c(dbh: float, p) -> float:
    """Aboveground biomass of one tree (kgC).

    B = (pi/4) * D^2 * H(D) * f * rho / sigma, the FORMIND stem-volume form,
    where f is the stem form factor, rho wood density and sigma the fraction of
    aboveground biomass held in the stem.
    """
    if dbh <= 0.0:
        return 0.0
    odm = (
        math.pi
        * 0.25
        * dbh**2
        * height(dbh, p)
        * p.form_factor
        * p.wood_density
        / p.stem_fraction
    )
    return odm * KG_C_PER_KG_ODM


def _dbiomass_ddbh(dbh: float, p) -> float:
    """dB/dD (kgC m-1), analytic derivative of `aboveground_biomass_c`."""
    if dbh <= 0.0:
        return 0.0
    coefficient = (
        math.pi * 0.25 * p.form_factor * p.wood_density / p.stem_fraction * p.h0 * KG_C_PER_KG_ODM
    )
    return coefficient * (2.0 + p.h1) * dbh ** (1.0 + p.h1)


def diameter_increment(dbh: float, biomass_increment_c: float, p) -> float:
    """Convert an aboveground carbon increment (kgC) into a diameter increment (m).

    This is FORMIND's growth step inverted: carbon is earned by photosynthesis,
    then spent on becoming thicker, with the allometry deciding how much thicker.
    """
    if biomass_increment_c <= 0.0 or dbh <= 0.0:
        return 0.0
    slope = _dbiomass_ddbh(dbh, p)
    return biomass_increment_c / slope if slope > 0.0 else 0.0


def diameter_from_biomass(biomass_c: float, p) -> float:
    """Invert the biomass allometry analytically. Used to size new recruits."""
    if biomass_c <= 0.0:
        return 0.0
    coefficient = (
        math.pi * 0.25 * p.form_factor * p.wood_density / p.stem_fraction * p.h0 * KG_C_PER_KG_ODM
    )
    return (biomass_c / coefficient) ** (1.0 / (2.0 + p.h1))
