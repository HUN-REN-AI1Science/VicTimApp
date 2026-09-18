"""One tile: the unit of simulation, and the place the coupling is enforced.

A tile is a FORMIND patch -- 20 m x 20 m by default -- holding one soil column,
one light profile, and any number of vegetation modules. `Tile.step_day` fixes
the order of operations that makes the coupling physical:

    1. rain enters the shared soil column
    2. EVERY module's canopy is resolved in ONE light profile
    3. every module states its water demand
    4. the shared column grants water, pro rata if it cannot meet total demand
    5. every module grows on the light and water it actually received
    6. litter and nitrogen uptake pass through the shared column
    7. the column decomposes

Steps 2 and 4 are the whole scientific argument for this design. A tile that
resolved light or water twice -- once per model -- would double-count the
resource and produce more total production than the site receives.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable

import numpy as np

from .cohort import CanopyElement
from .disturbance import Defoliation
from .light import LightProfile, LightResult
from .soil import SoilColumn, SoilParameters
from .units import DAYS_PER_YEAR, DEFAULT_TILE_SIZE_M
from .weather import DayWeather

__all__ = ["Tile", "StepContext", "VegetationModule", "SeedRain"]


@dataclass
class SeedRain:
    """Seeds arriving at this tile this year, in seeds m-2 y-1, keyed by PFT.

    `incoming` is what the tile receives (external rain plus its own plants'
    `outgoing` from the year before -- a tile only ever seeds itself);
    `outgoing` is what its own plants produced this year.
    """

    incoming: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    outgoing: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    external: dict[str, float] = field(default_factory=dict)
    """Constant background seed rain from outside the simulated region."""

    def offer(self, pft: str, seeds_per_m2: float) -> None:
        self.outgoing[pft] = self.outgoing.get(pft, 0.0) + seeds_per_m2

    def available(self, pft: str) -> float:
        return self.incoming.get(pft, 0.0) + self.external.get(pft, 0.0)

    def reset_incoming(self) -> None:
        self.incoming = defaultdict(float)

    def reset_outgoing(self) -> None:
        self.outgoing = defaultdict(float)


@dataclass
class StepContext:
    """Everything a vegetation module may read or mutate during one day.

    A module receives light and water it did not compute itself. That is the
    point: it cannot help but compete with the other module through them.
    """

    day: DayWeather
    day_index: int
    light: LightResult
    soil: SoilColumn
    tile_area_m2: float
    water_supply_fraction: float
    """Granted water / requested water, in [0, 1]. Shared drought limitation."""
    seed_rain: SeedRain
    rng: np.random.Generator
    disturbances: list[Defoliation] = field(default_factory=list)
    """Tile-level events this day, emitted by any module, seen by all of them."""

    @property
    def is_year_end(self) -> bool:
        return (self.day_index + 1) % DAYS_PER_YEAR == 0


@runtime_checkable
class VegetationModule(Protocol):
    """The contract `formind` and `grassmind` implement.

    Deliberately narrow: a module cannot see the other module, only the shared
    light and soil. Cross-model effects (canopy shading, sward suppression of
    tree seedlings) therefore have to travel through real resources.
    """

    name: str

    def canopy_elements(self) -> list[CanopyElement]:
        """Leaf area this module puts into the shared vertical profile."""

    def emit_disturbances(self, day: DayWeather) -> list[Defoliation]:
        """Tile-level events this module triggers today, before anyone steps.

        Optional: `Tile.step_day` skips modules that do not define it.
        """

    def water_demand_mm(self, day: DayWeather, light: LightResult) -> float:
        """Transpiration this module would like today (mm)."""

    def step_day(self, ctx: StepContext) -> None:
        """Photosynthesis, respiration, allocation, litter, nitrogen uptake."""

    def step_year(self, ctx: StepContext) -> None:
        """Mortality, recruitment, cohort bookkeeping."""

    def diagnostics(self, area_m2: float) -> dict:
        """Scalar outputs for charts and tests, ALL expressed per m2 of ground.

        Per-m2 rather than per-tile so that a chart means the same thing whatever
        tile size a run uses, and so that no caller has to remember which
        quantities were already normalised.
        """


@dataclass
class Tile:
    """A single 20 m x 20 m patch."""

    size_m: float = DEFAULT_TILE_SIZE_M
    soil: SoilColumn = field(default_factory=lambda: SoilColumn(SoilParameters()))
    modules: list[VegetationModule] = field(default_factory=list)
    seed_rain: SeedRain = field(default_factory=SeedRain)

    canopy_top_m: float = 0.0
    """Height of the tallest leaf in this tile (m), as of the last `step_day`."""

    @property
    def area_m2(self) -> float:
        return self.size_m * self.size_m

    def add_module(self, module: VegetationModule) -> None:
        self.modules.append(module)

    def module(self, name: str) -> VegetationModule:
        for m in self.modules:
            if m.name == name:
                return m
        raise KeyError(f"tile has no module named {name!r}")

    # ------------------------------------------------------------- stepping --

    def step_day(
        self,
        day: DayWeather,
        day_index: int,
        rng: np.random.Generator,
    ) -> LightResult:
        """Advance this tile by one day. Returns the resolved light climate."""
        # 0. Disturbances are collected BEFORE anyone grows, so that every module
        #    sees the same events regardless of the order modules were added.
        disturbances: list[Defoliation] = []
        for module in self.modules:
            emit = getattr(module, "emit_disturbances", None)
            if emit is not None:
                disturbances.extend(emit(day))

        # 1. Rain and atmospheric nitrogen into the shared column.
        self.soil.add_precipitation(day.precipitation_mm)
        self.soil.add_deposition_n()

        # 2. ONE light profile for every module in the tile.
        profile = LightProfile(self.area_m2)
        for module in self.modules:
            profile.add(module.canopy_elements())
        light = profile.resolve(day.par_umol_m2_s)

        # Read off the profile that was just built, so it costs nothing beyond
        # the max: asking the modules for their canopy elements a second time
        # would double the most expensive call in the day.
        self.canopy_top_m = max((e.top_m for e in profile.elements), default=0.0)

        # 3./4. Water demand is pooled, then granted pro rata by the shared column.
        demands = [max(0.0, m.water_demand_mm(day, light)) for m in self.modules]
        total_demand = sum(demands)
        granted = self.soil.withdraw_water(total_demand) if total_demand > 0.0 else 0.0
        supply_fraction = granted / total_demand if total_demand > 0.0 else 1.0

        # Bare-soil evaporation scales with the light actually reaching the ground.
        if light.incident_par > 0.0:
            exposure = light.floor_par / light.incident_par
            self.soil.withdraw_water(
                0.25 * day.potential_evapotranspiration_mm * exposure, transpiration=False
            )

        ctx = StepContext(
            day=day,
            day_index=day_index,
            light=light,
            soil=self.soil,
            tile_area_m2=self.area_m2,
            water_supply_fraction=supply_fraction,
            seed_rain=self.seed_rain,
            rng=rng,
            disturbances=disturbances,
        )

        # 5./6. Modules grow on what they received and return litter to the column.
        for module in self.modules:
            module.step_day(ctx)

        # 7. Decomposition closes the day.
        self.soil.decompose(day.temperature_c)

        if ctx.is_year_end:
            for module in self.modules:
                module.step_year(ctx)

        return light

    # ---------------------------------------------------------- diagnostics --

    def diagnostics(self, light: LightResult | None = None) -> dict:
        out: dict = {
            "soil_c": self.soil.total_c,
            "soil_n": self.soil.total_n,
            "mineral_n": self.soil.mineral_n,
            "soil_water_mm": self.soil.water_mm,
            "relative_water_content": self.soil.relative_water_content,
            "leached_n": self.soil.cumulative_leached_n,
            "canopy_top_m": self.canopy_top_m,
        }
        if light is not None:
            out["lai"] = light.total_lai
            out["floor_light_fraction"] = (
                light.floor_par / light.incident_par if light.incident_par > 0 else 1.0
            )
        for module in self.modules:
            for key, value in module.diagnostics(self.area_m2).items():
                out[f"{module.name}_{key}"] = value
        return out
