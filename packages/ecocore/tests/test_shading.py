"""Lateral shading tests.

The per-tile light identity `sum(absorbed) + floor == incident` is unaffected by
shading -- `test_light.py` still owns it -- because a kernel only changes what
`incident` is. What these tests own is the grid-level statement that replaces it:
a shaded region absorbs less than the open sky delivers over its area, never
more, and no tile is ever brightened by a neighbour.
"""

import numpy as np
import pytest

from ecocore import (
    Grid,
    NoLateralShading,
    SkyViewShading,
    SoilColumn,
    SoilParameters,
    Tile,
    run_simulation,
    synthetic_weather,
)

from test_grid import StubModule


def build_grid(nx, ny, shading=None, leaf_area=400.0):
    def factory(x, y):
        return Tile(soil=SoilColumn(SoilParameters()), modules=[StubModule(leaf_area)])

    return Grid.build(nx, ny, factory, shading=shading or NoLateralShading())


def with_canopy(grid, height_m, only=None):
    """Set every tile's published canopy height, or only the listed cells."""
    for tile in grid.tiles:
        if only is None or (tile.x, tile.y) in only:
            tile.canopy_top_m = height_m
    return grid


# ------------------------------------------------------------- open horizons --


def test_no_lateral_shading_leaves_every_tile_under_open_sky():
    grid = with_canopy(build_grid(3, 3, NoLateralShading()), 30.0)
    assert set(grid.shading.sky_fractions(grid).values()) == {1.0}


def test_a_lone_tile_has_nothing_to_shade_it():
    """A 1x1 grid must be unshaded whatever kernel it is given.

    Off-grid neighbours count as open sky, so the single-tile run stays the
    reference trajectory that multi-tile runs are compared against.
    """
    grid = with_canopy(build_grid(1, 1, SkyViewShading()), 40.0)
    assert grid.shading.sky_fractions(grid) == {(0, 0): 1.0}


def test_bare_neighbours_do_not_shade():
    grid = build_grid(3, 3, SkyViewShading())  # every canopy_top_m still 0.0
    assert grid.shading.sky_fractions(grid) == pytest.approx(
        {(x, y): 1.0 for x in range(3) for y in range(3)}
    )


# ------------------------------------------------------------------ geometry --


def test_a_taller_neighbour_takes_more_sky():
    fractions = []
    for height in (5.0, 15.0, 30.0):
        grid = with_canopy(build_grid(2, 1, SkyViewShading()), height, only={(1, 0)})
        fractions.append(grid.shading.sky_fractions(grid)[(0, 0)])

    assert all(f < 1.0 for f in fractions)
    assert fractions[0] > fractions[1] > fractions[2]


def test_a_more_distant_neighbour_takes_less_sky():
    near = with_canopy(build_grid(4, 1, SkyViewShading()), 30.0, only={(1, 0)})
    far = with_canopy(build_grid(4, 1, SkyViewShading()), 30.0, only={(2, 0)})
    assert near.shading.sky_fractions(near)[(0, 0)] < far.shading.sky_fractions(far)[(0, 0)]


def test_a_neighbour_beyond_the_radius_is_not_seen():
    grid = with_canopy(build_grid(5, 1, SkyViewShading(radius_tiles=2)), 30.0, only={(3, 0)})
    assert grid.shading.sky_fractions(grid)[(0, 0)] == 1.0


def test_the_middle_of_a_tall_stand_is_the_darkest_place_in_it():
    """Interior, edge and corner tiles must rank by how much horizon they have."""
    grid = with_canopy(build_grid(3, 3, SkyViewShading()), 30.0)
    fractions = grid.shading.sky_fractions(grid)

    centre = fractions[(1, 1)]
    edges = [fractions[(1, 0)], fractions[(0, 1)], fractions[(2, 1)], fractions[(1, 2)]]
    corners = [fractions[(0, 0)], fractions[(2, 0)], fractions[(0, 2)], fractions[(2, 2)]]

    assert centre < min(edges)
    assert max(edges) < min(corners)
    assert max(corners) < 1.0
    # Symmetry: the grid is square and uniformly tall, so like positions match.
    assert edges == pytest.approx([edges[0]] * 4)
    assert corners == pytest.approx([corners[0]] * 4)


def test_sky_fraction_stays_within_bounds_under_an_extreme_canopy():
    grid = with_canopy(build_grid(3, 3, SkyViewShading(radius_tiles=1)), 5000.0)
    assert all(0.0 <= f <= 1.0 for f in grid.shading.sky_fractions(grid).values())


# -------------------------------------------------------------- conservation --


def absorbed_and_floor(grid, weather, years=1):
    """Total light intercepted over a run, as a multiple of one tile's open sky."""
    rng = np.random.default_rng(3)
    total = 0.0
    incident = 0.0
    for day_index in range(years * 365):
        day = weather.day(day_index)
        sky = grid.shading.sky_fractions(grid)
        for tile in grid.tiles:
            light = tile.step_day(day, day_index, rng, sky_fraction=sky[(tile.x, tile.y)])
            total += light.absorbed_total + light.floor_par
            incident += day.par_umol_m2_s
    return total, incident


def test_a_shaded_region_intercepts_less_than_the_sky_delivers():
    """The grid-level restatement of the light contract.

    Per tile, absorbed + floor still equals that tile's incident exactly. Across
    the grid, a shaded region must intercept strictly LESS than the open sky over
    the same area -- and an unshaded one exactly as much.
    """
    weather = synthetic_weather(1, seed=4)

    open_grid = with_canopy(build_grid(3, 3, NoLateralShading()), 25.0)
    open_total, open_incident = absorbed_and_floor(open_grid, weather)
    assert open_total == pytest.approx(open_incident, rel=1e-9)

    shaded = with_canopy(build_grid(3, 3, SkyViewShading()), 25.0)
    shaded_total, shaded_incident = absorbed_and_floor(shaded, weather)
    assert shaded_total < shaded_incident
    assert shaded_total > 0.0


def test_run_simulation_applies_and_records_the_sky_fraction():
    """The effect must survive `run_simulation`, not just a direct kernel call."""
    weather = synthetic_weather(1, seed=5)

    def final(shading):
        grid = with_canopy(build_grid(3, 3, shading), 25.0)
        result = run_simulation(grid, weather, years=1, record_every=90, seed=5)
        return result.series(1, 1)[-1]

    lit = final(NoLateralShading())
    dark = final(SkyViewShading())

    assert lit["sky_view_fraction"] == 1.0
    assert dark["sky_view_fraction"] < 1.0
    # `floor_light_fraction` is a fraction of the tile's OWN incident, and this
    # stub's canopy does not respond to light, so both are unchanged. What fell
    # is the absolute irradiance on the ground: fraction * sky_view_fraction.
    assert dark["floor_light_fraction"] == pytest.approx(lit["floor_light_fraction"])
    assert dark["canopy_top_m"] == pytest.approx(lit["canopy_top_m"])
    assert (
        dark["floor_light_fraction"] * dark["sky_view_fraction"]
        < lit["floor_light_fraction"] * lit["sky_view_fraction"]
    )
