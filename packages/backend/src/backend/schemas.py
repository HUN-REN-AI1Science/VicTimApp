"""Request and response shapes.

These Pydantic models are the contract between the simulation packages and the
browser. The frontend generates its TypeScript types from the OpenAPI schema
FastAPI derives from them, so a field added here reaches the UI without a second
definition drifting out of sync.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

__all__ = [
    "SiteConfig",
    "WeatherConfig",
    "GridConfig",
    "MowingConfig",
    "GrazingConfig",
    "FertilisationConfig",
    "ManagementConfig",
    "TileVegetationConfig",
    "TileTypeConfig",
    "VegetationConfig",
    "ScenarioConfig",
    "JobStatus",
    "SimulationResults",
    "default_tile_types",
]


class SiteConfig(BaseModel):
    """Soil properties of every tile in the run."""

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


class GridConfig(BaseModel):
    """The tiled region. Defaults to a single, unshaded, self-seeding tile.

    Both between-tile processes are off by default, so a multi-tile run
    reproduces N copies of the single-tile trajectory until one is switched on.
    """

    nx: int = Field(1, ge=1, le=16)
    ny: int = Field(1, ge=1, le=16)
    tile_size_m: float = Field(20.0, gt=0.0, le=100.0)
    dispersal: Literal["none", "exponential"] = "none"
    dispersal_mean_distance_m: float = Field(30.0, gt=0.0)
    dispersal_radius_tiles: int = Field(2, ge=1, le=6)
    lateral_shading: Literal["none", "sky_view"] = "none"
    """Whether a tile's neighbours take part of its sky. See `ecocore.shading`."""
    shading_radius_tiles: int = Field(2, ge=1, le=6)


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


class TileVegetationConfig(BaseModel):
    """What stands on a tile at year zero.

    Per tile type, not per region: an abandoned field and a planted stand differ
    in what is on the ground, not in what a beech is. Species biology lives in
    the PFT tables on `VegetationConfig`, which stay region-wide.
    """

    include_forest: bool = True
    include_grassland: bool = True
    initial_sward_density_per_m2: float = Field(300.0, ge=0.0)
    initial_trees_per_tile: int = Field(0, ge=0, le=500)
    initial_tree_pft: str = "mid"
    initial_tree_dbh: float = Field(0.05, gt=0.0, le=1.0)


class TileTypeConfig(BaseModel):
    """A named land-use type: what grows on a tile and what is done to it.

    The unit of per-tile configuration. Twenty-five tiles are not twenty-five
    forms -- they are a handful of types and an assignment of tiles to them, so
    editing "meadow" edits every meadow at once.

    A type owns exactly the two things that can differ between two tiles of one
    region: its management schedule and its initial vegetation. Soil, weather,
    the grid geometry and the PFT tables are properties of the region and are
    deliberately not here -- a tile with its own soil would be a second site, not
    a second land use.
    """

    id: str = Field(..., min_length=1, max_length=40)
    label: str = Field(..., min_length=1, max_length=60)
    colour: str = Field("#9aa87e", pattern=r"^#[0-9a-fA-F]{6}$")
    """How the region map draws tiles of this type before there is output to colour."""
    management: ManagementConfig = Field(default_factory=ManagementConfig)
    vegetation: TileVegetationConfig = Field(default_factory=TileVegetationConfig)


def default_tile_types() -> list[TileTypeConfig]:
    """The palette every scenario starts with, one type per management preset.

    Generated from the presets rather than written out twice, so a type and the
    preset it is named after cannot drift apart. `Forest` is the one addition:
    it is unmanaged like `Abandoned` but starts with a stand on it, which is the
    only way to give a region a wooded edge at year zero.
    """
    return [
        TileTypeConfig(
            id="abandoned", label="Abandoned", colour="#a8ab7c",
            management=ManagementConfig(preset="abandoned"),
        ),
        TileTypeConfig(
            id="meadow", label="Extensive meadow", colour="#c8d191",
            management=ManagementConfig(preset="extensive_meadow"),
        ),
        TileTypeConfig(
            id="intensive", label="Intensive meadow", colour="#dfe3a8",
            management=ManagementConfig(preset="intensive_meadow"),
        ),
        TileTypeConfig(
            id="pasture", label="Pasture", colour="#d3c68f",
            management=ManagementConfig(preset="pasture"),
        ),
        TileTypeConfig(
            id="forest", label="Forest", colour="#3f6b4f",
            management=ManagementConfig(preset="abandoned"),
            vegetation=TileVegetationConfig(
                initial_trees_per_tile=60, initial_tree_dbh=0.15, initial_tree_pft="mid"
            ),
        ),
    ]


class VegetationConfig(BaseModel):
    """Vegetation properties of the whole region: the seed source and the PFTs."""

    external_seed_rain: dict[str, float] = Field(
        default_factory=lambda: {
            "grass": 400.0, "forb": 250.0, "legume": 150.0,
            "pioneer": 8.0, "mid": 4.0, "late": 2.0,
        },
        description="Seeds m-2 y-1 arriving from outside the simulated region.",
    )
    tree_pft_overrides: dict[str, dict[str, float]] = Field(default_factory=dict)
    grass_pft_overrides: dict[str, dict[str, float]] = Field(default_factory=dict)


class ScenarioConfig(BaseModel):
    """Everything needed to reproduce a run.

    Split three ways, which is the shape of the model rather than of the form:

    * **region-wide** -- `grid`, `site`, `weather`, `vegetation`. One soil, one
      climate, one set of PFTs. A tile that carried its own soil column would be
      a second site, and `ecocore` guarantees exactly one column per tile.
    * **per tile type** -- `tile_types`. Management and initial vegetation, the
      only two things that legitimately differ between two tiles of one region.
    * **per tile** -- `tile_assignment`, which is nothing but a type name.
    """

    name: str = "Untitled scenario"
    years: int = Field(60, ge=1, le=500)
    record_every_days: int = Field(365, ge=1, le=3650)
    seed: int = 1
    grid: GridConfig = Field(default_factory=GridConfig)
    site: SiteConfig = Field(default_factory=SiteConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    vegetation: VegetationConfig = Field(default_factory=VegetationConfig)

    tile_types: list[TileTypeConfig] = Field(default_factory=default_tile_types)
    """The land-use palette. Must be non-empty and its ids unique."""

    tile_assignment: list[str] = Field(default_factory=list)
    """One type id per tile in row-major order (`y * nx + x`), or empty.

    Empty means every tile takes `tile_types[0]`, which is how a client that has
    never heard of tile types still gets a uniform, runnable region. A partial
    assignment is rejected rather than padded: silently filling in the tiles a
    caller forgot would let a truncated request run as a different scenario than
    the one it described.
    """

    @model_validator(mode="after")
    def _check_tile_types(self) -> "ScenarioConfig":
        if not self.tile_types:
            raise ValueError("tile_types must not be empty")
        ids = [t.id for t in self.tile_types]
        if len(set(ids)) != len(ids):
            raise ValueError("tile type ids must be unique")
        if self.tile_assignment:
            expected = self.grid.nx * self.grid.ny
            if len(self.tile_assignment) != expected:
                raise ValueError(
                    f"tile_assignment has {len(self.tile_assignment)} entries, "
                    f"but the grid has {expected} tiles"
                )
            unknown = set(self.tile_assignment) - set(ids)
            if unknown:
                raise ValueError(f"tile_assignment names unknown tile types: {sorted(unknown)}")
        return self

    def tile_type_at(self, x: int, y: int) -> TileTypeConfig:
        """The type governing tile (x, y). Row-major, matching `tile_assignment`."""
        if not self.tile_assignment:
            return self.tile_types[0]
        wanted = self.tile_assignment[y * self.grid.nx + x]
        return next(t for t in self.tile_types if t.id == wanted)


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
    tiles: list[dict]
    """One entry per tile: {"x", "y", "series": [{variable: value}, ...]}."""
