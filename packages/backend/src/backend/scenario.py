"""Turn a `ScenarioConfig` into a runnable `ecocore.Tile`.

This module is the only place that knows how the API's vocabulary maps onto the
three simulation packages, which keeps the model packages free of any awareness
that a web API exists.
"""

from __future__ import annotations

from dataclasses import replace

from ecocore import SoilColumn, SoilParameters, Tile, WeatherSeries, synthetic_weather
from formind import DEFAULT_TREE_PFTS, ForestModule, TreePFT
from grassmind import (
    DEFAULT_GRASS_PFTS,
    FertilisationEvent,
    GrassPFT,
    GrazingPeriod,
    GrasslandModule,
    ManagementSchedule,
    MowingEvent,
)

from .schemas import ManagementConfig, ScenarioConfig

__all__ = ["build_tile", "build_weather", "build_management", "tile_recorder"]


def build_weather(config: ScenarioConfig) -> WeatherSeries:
    w = config.weather
    return synthetic_weather(
        years=w.years_of_variability,
        latitude_deg=w.latitude_deg,
        mean_temperature_c=w.mean_temperature_c,
        temperature_amplitude_c=w.temperature_amplitude_c,
        annual_precipitation_mm=w.annual_precipitation_mm,
        peak_radiation_mj_m2=w.peak_radiation_mj_m2,
        seed=w.seed,
    )


def build_management(m: ManagementConfig) -> ManagementSchedule:
    """Resolve a preset, or assemble the explicit lists.

    An explicit list always wins over the preset, so the UI can start from a
    preset and then edit individual events without having to switch mode.
    """
    if not (m.mowing or m.grazing or m.fertilisation):
        presets = {
            "abandoned": ManagementSchedule.abandoned,
            "extensive_meadow": ManagementSchedule.extensive_meadow,
            "intensive_meadow": ManagementSchedule.intensive_meadow,
            "pasture": ManagementSchedule.pasture,
            "custom": ManagementSchedule.abandoned,
        }
        return presets[m.preset]()

    return ManagementSchedule(
        mowing=[
            MowingEvent(
                day_of_year=e.day_of_year,
                cut_height_m=e.cut_height_m,
                removal_fraction=e.removal_fraction,
                woody_kill_height_m=e.woody_kill_height_m,
            )
            for e in m.mowing
        ],
        grazing=[
            GrazingPeriod(
                start_day=e.start_day,
                end_day=e.end_day,
                intake_fraction_per_day=e.intake_fraction_per_day,
                return_fraction=e.return_fraction,
                min_height_m=e.min_height_m,
                woody_kill_height_m=e.woody_kill_height_m,
                woody_kill_fraction=e.woody_kill_fraction,
            )
            for e in m.grazing
        ],
        fertilisation=[
            FertilisationEvent(day_of_year=e.day_of_year, nitrogen_kg_m2=e.nitrogen_kg_m2)
            for e in m.fertilisation
        ],
    )


def _apply_overrides(defaults, overrides: dict[str, dict[str, float]]):
    """Return PFTs with the UI's edits applied, leaving the defaults untouched."""
    out = []
    for pft in defaults:
        edits = overrides.get(pft.id)
        out.append(replace(pft, **edits) if edits else replace(pft))
    return out


def build_tile(config: ScenarioConfig) -> Tile:
    tree_pfts: list[TreePFT] = _apply_overrides(
        DEFAULT_TREE_PFTS, config.vegetation.tree_pft_overrides
    )
    grass_pfts: list[GrassPFT] = _apply_overrides(
        DEFAULT_GRASS_PFTS, config.vegetation.grass_pft_overrides
    )
    schedule = build_management(config.management)
    v = config.vegetation
    s = config.site

    soil = SoilColumn(
        SoilParameters(
            depth_m=s.depth_m,
            sand_fraction=s.sand_fraction,
            clay_fraction=s.clay_fraction,
            field_capacity_mm=s.field_capacity_mm,
            wilting_point_mm=s.wilting_point_mm,
            initial_active_c=s.initial_active_c,
            initial_slow_c=s.initial_slow_c,
            initial_passive_c=s.initial_passive_c,
            initial_mineral_n=s.initial_mineral_n,
        )
    )
    tile = Tile(soil=soil, size_m=s.tile_size_m)
    if v.include_grassland:
        tile.add_module(
            GrasslandModule.sown_sward(
                pfts=grass_pfts,
                plants_per_m2=v.initial_sward_density_per_m2,
                management=schedule,
                tile_area_m2=s.tile_size_m**2,
            )
        )
    if v.include_forest:
        forest = ForestModule.bare_ground(tree_pfts)
        if v.initial_trees_per_tile > 0:
            forest.seed_stand(v.initial_tree_pft, v.initial_trees_per_tile, v.initial_tree_dbh)
        tile.add_module(forest)
    tile.seed_rain.external = dict(v.external_seed_rain)
    return tile


def tile_recorder(tile: Tile) -> dict:
    """Capture vertical structure alongside the scalar diagnostics.

    Feeds the stand-structure view, which is the picture that makes the shared
    canopy legible: trees and the grass beneath them in one diagram.
    """
    record: dict = {}
    for module in tile.modules:
        if isinstance(module, ForestModule):
            record["stand_profile"] = module.stand_profile()
            record["dbh_histogram"] = module.dbh_histogram()
        if isinstance(module, GrasslandModule):
            record["sward_profile"] = module.sward_profile()
    return record
