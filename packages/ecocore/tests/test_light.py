"""The coupling's load-bearing invariants live here.

`test_energy_is_conserved` is the automated guard against the double-counting
failure mode: if anyone ever resolves light per-model instead of per-tile, the
absorbed total will exceed the incident radiation and this test fails.
"""

import math

import pytest

from ecocore.cohort import CanopyElement
from ecocore.light import LightProfile, compute_light


def tree(key="tree", leaf_area=1600.0, k=0.7):
    return CanopyElement(key=key, base_m=5.0, top_m=20.0, leaf_area_m2=leaf_area, k=k)


def grass(key="grass", leaf_area=800.0, k=0.6):
    return CanopyElement(key=key, base_m=0.0, top_m=0.4, leaf_area_m2=leaf_area, k=k)


def test_energy_is_conserved():
    result = compute_light([tree(), grass()], incident_par=1000.0, tile_area_m2=400.0)
    assert result.absorbed_total + result.floor_par == pytest.approx(1000.0, rel=1e-9)


def test_energy_conserved_across_many_configurations():
    for n_elements in (1, 3, 12):
        elements = [
            CanopyElement(
                key=i,
                base_m=0.2 * i,
                top_m=0.2 * i + 1.5 + i,
                leaf_area_m2=100.0 * (i + 1),
                k=0.4 + 0.05 * (i % 6),
            )
            for i in range(n_elements)
        ]
        result = compute_light(elements, 900.0, 400.0)
        assert result.absorbed_total + result.floor_par == pytest.approx(900.0, rel=1e-9)


def test_empty_canopy_passes_all_light_to_the_floor():
    result = compute_light([], 800.0, 400.0)
    assert result.floor_par == 800.0
    assert result.absorbed_total == 0.0


def test_extinction_is_monotonic_in_leaf_area():
    previous = math.inf
    for leaf_area in (100.0, 400.0, 1600.0, 6400.0):
        result = compute_light([tree(leaf_area=leaf_area)], 1000.0, 400.0)
        assert result.floor_par < previous
        previous = result.floor_par


def test_floor_light_follows_lambert_beer():
    """A single uniform layer must reproduce exp(-k * LAI) exactly."""
    element = CanopyElement(key="single", base_m=0.0, top_m=0.5, leaf_area_m2=800.0, k=0.5)
    result = compute_light([element], 1000.0, 400.0)
    expected = 1000.0 * math.exp(-0.5 * 2.0)
    assert result.floor_par == pytest.approx(expected, rel=1e-9)


def test_grass_under_trees_receives_less_than_grass_alone():
    """The whole point of one shared profile: the overstorey must shade the sward."""
    alone = compute_light([grass()], 1000.0, 400.0)
    shaded = compute_light([tree(), grass()], 1000.0, 400.0)
    assert shaded.mean_incident_par["grass"] < 0.3 * alone.mean_incident_par["grass"]
    assert shaded.absorbed_par["grass"] < alone.absorbed_par["grass"]


def test_taller_cohort_receives_more_light_than_shorter_one():
    tall = CanopyElement(key="tall", base_m=8.0, top_m=16.0, leaf_area_m2=800.0, k=0.6)
    short = CanopyElement(key="short", base_m=0.0, top_m=4.0, leaf_area_m2=800.0, k=0.6)
    result = compute_light([tall, short], 1000.0, 400.0)
    assert result.mean_incident_par["tall"] > result.mean_incident_par["short"]


def test_profile_accumulates_modules_before_resolving():
    profile = LightProfile(400.0)
    profile.add([tree()])
    profile.add([grass()])
    combined = profile.resolve(1000.0)
    assert set(combined.absorbed_par) == {"tree", "grass"}
    assert combined.absorbed_total + combined.floor_par == pytest.approx(1000.0, rel=1e-9)


def test_degenerate_crown_still_intercepts():
    """Seedlings and very short grass have zero crown depth; they must not vanish."""
    flat = CanopyElement(key="seedling", base_m=0.3, top_m=0.3, leaf_area_m2=400.0, k=0.5)
    result = compute_light([flat], 1000.0, 400.0)
    assert result.absorbed_par["seedling"] > 0.0
    assert result.floor_par < 1000.0


def test_rejects_invalid_geometry():
    with pytest.raises(ValueError):
        CanopyElement(key="bad", base_m=5.0, top_m=1.0, leaf_area_m2=10.0, k=0.5)
    with pytest.raises(ValueError):
        CanopyElement(key="bad", base_m=0.0, top_m=1.0, leaf_area_m2=10.0, k=1.5)
    with pytest.raises(ValueError):
        compute_light([tree()], 1000.0, 0.0)
