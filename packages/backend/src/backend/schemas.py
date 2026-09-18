"""Request and response shapes.

These Pydantic models are the contract between the simulation packages and the
browser. The frontend generates its TypeScript types from the OpenAPI schema
FastAPI derives from them, so a field added here reaches the UI without a second
definition drifting out of sync.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "SiteConfig",
    "WeatherConfig",
    "MowingConfig",
    "GrazingConfig",
    "FertilisationConfig",
    "ManagementConfig",
    "VegetationConfig",
    "ScenarioConfig",
    "JobStatus",
    "SimulationResults",
]


class SiteConfig(BaseModel):
    """The tile: its soil properties and its size."""

    tile_size_m: float = Field(20.0, gt=0.0, le=100.0)
    depth_m: float = Field(1.0, gt=0.0, le=5.0)
    sand_fraction: float = Field(0.4, ge=0.0, le=1.0)
    clay_fraction: float = Field(0.2, ge=0.0, le=1.0)
    field_capacity_mm: float = Field(300.0, gt=0.0)
    wilting_point_mm: float = Field(120.0, ge=0.0)
    initial_active_c: float = Field(0.15, ge=0.0)
    initial_slow_c: float = Field(2.5, ge=0.0)
    initial_passive_c: float = Field(4.0, ge=0.0)
    initial_mineral_n: float = Field(0.004, ge=0.0)


class WeatherConfig(BaseModel):
    """Synthetic climate. Replace with a loader when driving from real data."""

    latitude_deg: float = Field(51.0, ge=-66.0, le=66.0)
    mean_temperature_c: float = 9.0
    temperature_amplitude_c: float = Field(9.0, ge=0.0)
    annual_precipitation_mm: float = Field(700.0, gt=0.0)
    peak_radiation_mj_m2: float = Field(22.0, gt=0.0)
    years_of_variability: int = Field(5, ge=1, le=50)
    seed: int = 0


class MowingConfig(BaseModel):
    day_of_year: int = Field(..., ge=1, le=365)
    cut_height_m: float = Field(0.07, gt=0.0, le=1.0)
    removal_fraction: float = Field(0.9, ge=0.0, le=1.0)
    woody_kill_height_m: float = Field(0.6, ge=0.0, le=5.0)


class GrazingConfig(BaseModel):
    start_day: int = Field(..., ge=1, le=365)
    end_day: int = Field(..., ge=1, le=365)
    intake_fraction_per_day: float = Field(0.02, ge=0.0, le=0.5)
    return_fraction: float = Field(0.4, ge=0.0, le=1.0)
    min_height_m: float = Field(0.04, ge=0.0)
    woody_kill_height_m: float = Field(0.4, ge=0.0, le=5.0)
    woody_kill_fraction: float = Field(0.02, ge=0.0, le=1.0)


class FertilisationConfig(BaseModel):
    day_of_year: int = Field(..., ge=1, le=365)
    nitrogen_kg_m2: float = Field(0.005, ge=0.0, le=0.05)


class ManagementConfig(BaseModel):
    """Grassland management. `preset` fills the lists when they are left empty."""

    preset: Literal["abandoned", "extensive_meadow", "intensive_meadow", "pasture", "custom"] = (
        "abandoned"
    )
    mowing: list[MowingConfig] = Field(default_factory=list)
    grazing: list[GrazingConfig] = Field(default_factory=list)
    fertilisation: list[FertilisationConfig] = Field(default_factory=list)


class VegetationConfig(BaseModel):
    """What stands on the tile at year zero, and the PFTs and seed rain it draws on."""

    include_forest: bool = True
    include_grassland: bool = True
    initial_sward_density_per_m2: float = Field(300.0, ge=0.0)
    initial_trees_per_tile: int = Field(0, ge=0, le=500)
    initial_tree_pft: str = "mid"
    initial_tree_dbh: float = Field(0.05, gt=0.0, le=1.0)
    external_seed_rain: dict[str, float] = Field(
        default_factory=lambda: {
            "grass": 400.0, "forb": 250.0, "legume": 150.0,
            "pioneer": 8.0, "mid": 4.0, "late": 2.0,
        },
        description="Seeds m-2 y-1 arriving from outside the simulated tile.",
    )
    tree_pft_overrides: dict[str, dict[str, float]] = Field(default_factory=dict)
    grass_pft_overrides: dict[str, dict[str, float]] = Field(default_factory=dict)


class ScenarioConfig(BaseModel):
    """Everything needed to reproduce a run: one tile, one soil, one climate."""

    name: str = "Untitled scenario"
    years: int = Field(60, ge=1, le=500)
    record_every_days: int = Field(365, ge=1, le=3650)
    seed: int = 1
    site: SiteConfig = Field(default_factory=SiteConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    management: ManagementConfig = Field(default_factory=ManagementConfig)
    vegetation: VegetationConfig = Field(default_factory=VegetationConfig)


class JobStatus(BaseModel):
    id: str
    name: str
    state: Literal["queued", "running", "done", "failed"]
    progress: float = Field(0.0, ge=0.0, le=1.0)
    simulated_days: int = 0
    total_days: int = 0
    created_at: str
    finished_at: str | None = None
    error: str | None = None


class SimulationResults(BaseModel):
    id: str
    scenario: ScenarioConfig
    recorded_days: list[int]
    years: list[float]
    series: list[dict]
