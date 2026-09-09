"""Carbon and nitrogen must be conserved to machine precision.

The soil column is shared by both plant models, so a conservation leak here would
silently create or destroy carbon that the whole coupled model is accounted in.
"""

import pytest

from ecocore.soil import LitterInput, SoilColumn, SoilParameters


def test_carbon_and_nitrogen_are_conserved_over_a_decade():
    soil = SoilColumn(SoilParameters())
    c0, n0 = soil.total_c, soil.total_n
    for _ in range(3650):
        soil.add_precipitation(2.0)
        soil.withdraw_water(1.8)
        soil.add_litter(LitterInput(carbon=8e-4, nitrogen=2e-5, lignin_fraction=0.25))
        soil.uptake_n(2e-5)
        soil.decompose(12.0)
    assert soil.carbon_balance_error(c0) == pytest.approx(0.0, abs=1e-9)
    assert soil.nitrogen_balance_error(n0) == pytest.approx(0.0, abs=1e-12)


def test_fixation_and_fertiliser_are_accounted_separately():
    soil = SoilColumn(SoilParameters())
    n0 = soil.total_n
    soil.add_fertiliser_n(0.005)
    soil.add_fixed_n(0.002)
    assert soil.cumulative_fertiliser_n == pytest.approx(0.005)
    assert soil.cumulative_fixed_n == pytest.approx(0.002)
    assert soil.nitrogen_balance_error(n0) == pytest.approx(0.0, abs=1e-15)


def test_drainage_leaches_mineral_nitrogen():
    """Without this loss pathway, mineral nitrogen accumulates without bound."""
    soil = SoilColumn(SoilParameters())
    n0 = soil.total_n
    soil.mineral_n = 0.05
    n0 += 0.05 - SoilParameters().initial_mineral_n
    before = soil.mineral_n
    soil.add_precipitation(500.0)
    assert soil.mineral_n < before
    assert soil.cumulative_leached_n > 0.0
    assert soil.nitrogen_balance_error(n0) == pytest.approx(0.0, abs=1e-15)


def test_no_drainage_means_no_leaching():
    soil = SoilColumn(SoilParameters())
    before = soil.mineral_n
    soil.add_precipitation(1.0)
    assert soil.mineral_n == before
    assert soil.cumulative_leached_n == 0.0


def test_water_cannot_be_drawn_below_wilting_point():
    soil = SoilColumn(SoilParameters())
    granted = soil.withdraw_water(10_000.0)
    assert granted == pytest.approx(soil.params.field_capacity_mm * 0.5 + 0.5 * soil.params.wilting_point_mm - soil.params.wilting_point_mm)
    assert soil.water_mm == pytest.approx(soil.params.wilting_point_mm)
    assert soil.plant_available_water_mm == 0.0
    assert soil.withdraw_water(50.0) == 0.0


def test_excess_rain_drains_rather_than_accumulating():
    soil = SoilColumn(SoilParameters())
    drainage = soil.add_precipitation(10_000.0)
    assert soil.water_mm == pytest.approx(soil.params.field_capacity_mm)
    assert drainage > 0.0
    assert soil.cumulative_drainage_mm == pytest.approx(drainage)


def test_litter_splits_by_lignin_to_nitrogen_ratio():
    """Woody, nitrogen-poor litter must land mostly in the slow structural pool."""
    rich = SoilColumn(SoilParameters())
    rich.add_litter(LitterInput(carbon=1.0, nitrogen=0.05, lignin_fraction=0.1))
    poor = SoilColumn(SoilParameters())
    poor.add_litter(LitterInput(carbon=1.0, nitrogen=0.004, lignin_fraction=0.4))
    assert rich.metabolic_c > poor.metabolic_c
    assert poor.structural_c > rich.structural_c


def test_decomposition_is_suppressed_when_cold_or_dry():
    warm = SoilColumn(SoilParameters())
    cold = SoilColumn(SoilParameters())
    assert warm.decay_modifier(20.0) > cold.decay_modifier(-5.0)
    dry = SoilColumn(SoilParameters())
    dry.withdraw_water(10_000.0)
    assert dry.decay_modifier(20.0) < warm.decay_modifier(20.0)


def test_rejects_impossible_water_parameters():
    with pytest.raises(ValueError):
        SoilParameters(field_capacity_mm=100.0, wilting_point_mm=200.0)
