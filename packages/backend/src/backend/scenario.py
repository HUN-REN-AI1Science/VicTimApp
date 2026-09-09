"""Turn a `ScenarioConfig` into a runnable `ecocore.Grid`.

This module is the only place that knows how the API's vocabulary maps onto the
three simulation packages, which keeps the model packages free of any awareness
that a web API exists.
"""

from __future__ import annotations

from dataclasses import replace

from ecocore import (
    ExponentialKernel,
    Grid,
    NoDispersal,
    NoLateralShading,
    SkyViewShading,
    SoilColumn,
    SoilParameters,
    Tile,
    WeatherSeries,
    synthetic_weather,
)
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

__all__ = ["build_grid", "build_weather", "build_management", "tile_recorder"]


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

    Takes one `ManagementConfig` rather than the whole scenario because a
    schedule now belongs to a tile type, not to the run.
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


def build_grid(config: ScenarioConfig) -> Grid:
    tree_pfts: list[TreePFT] = _apply_overrides(
        DEFAULT_TREE_PFTS, config.vegetation.tree_pft_overrides
    )
    grass_pfts: list[GrassPFT] = _apply_overrides(
        DEFAULT_GRASS_PFTS, config.vegetation.grass_pft_overrides
    )
    # One schedule per tile type, not per tile: twenty-five meadow tiles share
    # one `ManagementSchedule`. Safe because a schedule is read, never mutated,
    # during a run -- the same reason a single schedule could be shared across
    # every tile before types existed.
    schedules = {t.id: build_management(t.management) for t in config.tile_types}
    seed_rain = dict(config.vegetation.external_seed_rain)
    s = config.site

    def factory(x: int, y: int) -> Tile:
        tile_type = config.tile_type_at(x, y)
        v = tile_type.vegetation
        schedule = schedules[tile_type.id]
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
        tile = Tile(soil=soil, size_m=config.grid.tile_size_m)
        if v.include_grassland:
            tile.add_module(
                GrasslandModule.sown_sward(
                    pfts=grass_pfts,
                    plants_per_m2=v.initial_sward_density_per_m2,
                    management=schedule,
                    tile_area_m2=config.grid.tile_size_m**2,
                )
            )
        if v.include_forest:
            forest = ForestModule.bare_ground(tree_pfts)
            if v.initial_trees_per_tile > 0:
                forest.seed_stand(
                    v.initial_tree_pft, v.initial_trees_per_tile, v.initial_tree_dbh
                )
            tile.add_module(forest)
        tile.seed_rain.external = dict(seed_rain)
        return tile

    dispersal = (
        ExponentialKernel(
            mean_distance_m=config.grid.dispersal_mean_distance_m,
            radius_tiles=config.grid.dispersal_radius_tiles,
        )
        if config.grid.dispersal == "exponential"
        else NoDispersal()
    )
    shading = (
        SkyViewShading(radius_tiles=config.grid.shading_radius_tiles)
        if config.grid.lateral_shading == "sky_view"
        else NoLateralShading()
    )
    return Grid.build(
        config.grid.nx,
        config.grid.ny,
        factory,
        tile_size_m=config.grid.tile_size_m,
        dispersal=dispersal,
        shading=shading,
    )


def tile_recorder(tile: Tile) -> dict:
    """Capture vertical structure alongside the scalar diagnostics.

    Feeds the stand-structure view, which is the picture that makes the shared
    canopy legible: trees and the grass beneath them in one diagram.
    """
    record: dict = {}
    for module in tile.modules:
        if hasattr(module, "stand_profile"):
            record["stand_profile"] = module.stand_profile()
            record["dbh_histogram"] = module.dbh_histogram()
        if hasattr(module, "sward_profile"):
            record["sward_profile"] = module.sward_profile()
    return record
