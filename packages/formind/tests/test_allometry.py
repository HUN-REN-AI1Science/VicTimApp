"""Tree geometry must be self-consistent and invertible.

The growth step converts carbon into diameter through the derivative of the
biomass allometry, so an inconsistency between `aboveground_biomass_c` and
`diameter_increment` would show up as trees that grow at the wrong rate rather
than as an error.
"""

import pytest

from formind import allometry
from formind.pft import DEFAULT_TREE_PFTS


@pytest.mark.parametrize("p", DEFAULT_TREE_PFTS, ids=lambda p: p.id)
def test_biomass_diameter_roundtrip(p):
    for dbh in (0.005, 0.05, 0.3, 0.6):
        biomass = allometry.aboveground_biomass_c(dbh, p)
        assert allometry.diameter_from_biomass(biomass, p) == pytest.approx(dbh, rel=1e-9)


@pytest.mark.parametrize("p", DEFAULT_TREE_PFTS, ids=lambda p: p.id)
def test_increment_matches_the_biomass_curve(p):
    """A carbon increment must move the diameter to where the allometry says."""
    dbh = 0.25
    before = allometry.aboveground_biomass_c(dbh, p)
    gain = before * 0.001
    new_dbh = dbh + allometry.diameter_increment(dbh, gain, p)
    after = allometry.aboveground_biomass_c(new_dbh, p)
    assert after - before == pytest.approx(gain, rel=1e-3)


@pytest.mark.parametrize("p", DEFAULT_TREE_PFTS, ids=lambda p: p.id)
def test_geometry_is_monotonic_in_diameter(p):
    heights = [allometry.height(d, p) for d in (0.05, 0.2, 0.5, 0.9)]
    crowns = [allometry.crown_diameter(d, p) for d in (0.05, 0.2, 0.5, 0.9)]
    assert heights == sorted(heights)
    assert crowns == sorted(crowns)


@pytest.mark.parametrize("p", DEFAULT_TREE_PFTS, ids=lambda p: p.id)
def test_crown_sits_below_the_treetop(p):
    for dbh in (0.01, 0.2, 0.7):
        assert 0.0 <= allometry.crown_base(dbh, p) < allometry.height(dbh, p)


@pytest.mark.parametrize("p", DEFAULT_TREE_PFTS, ids=lambda p: p.id)
def test_promotion_diameter_lands_near_breast_height(p):
    """Seedlings are promoted at `initial_dbh`; that must be ~1.3 m tall.

    If it drifts far from breast height, the seedling bank either double-counts
    growth or teleports saplings into the canopy.
    """
    from formind.recruitment import BREAST_HEIGHT_M

    assert allometry.height(p.initial_dbh, p) == pytest.approx(BREAST_HEIGHT_M, rel=0.15)


def test_zero_and_negative_diameters_are_safe():
    p = DEFAULT_TREE_PFTS[0]
    assert allometry.height(0.0, p) == 0.0
    assert allometry.aboveground_biomass_c(0.0, p) == 0.0
    assert allometry.diameter_increment(0.0, 1.0, p) == 0.0
    assert allometry.diameter_from_biomass(-1.0, p) == 0.0


def test_dimensions_are_physically_plausible():
    """A 0.5 m diameter mid-successional tree should be a recognisable tree."""
    p = next(x for x in DEFAULT_TREE_PFTS if x.id == "mid")
    assert 20.0 < allometry.height(0.5, p) < 45.0
    assert 5.0 < allometry.crown_diameter(0.5, p) < 14.0
    # 0.5 m DBH, ~28 m tall, ~600 kg m-3 wood: on the order of a tonne of carbon.
    assert 500.0 < allometry.aboveground_biomass_c(0.5, p) < 3000.0
