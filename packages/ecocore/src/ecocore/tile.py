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

The only thing a neighbouring tile contributes is the irradiance arriving at step
2: `step_day` takes a `sky_fraction` that scales incident PAR, computed by
`ecocore.shading` from the neighbours' canopy heights. There is still exactly one
profile and one column here, and a tile stepped on its own is unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable

import numpy as np

from .cohort import CanopyElement
from .disturbance import Defoliation
from .dispersal import SeedRain
from .light import LightProfile, LightResult
from .soil import SoilColumn, SoilParameters
from .units import DAYS_PER_YEAR, DEFAULT_TILE_SIZE_M
from .weather import DayWeather

__all__ = ["Tile", "StepContext", "VegetationModule"]


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
    x: int = 0
    y: int = 0

    canopy_top_m: float = 0.0
    """Height of the tallest leaf in this tile (m), as of the last `step_day`.

    The one piece of a tile's state a NEIGHBOURING tile is allowed to see, and
    only through `shading.LateralShading`, which turns it into a scalar sky view
    factor. A scalar height is not species biology -- ecocore never learns what
    grew to that height.
    """

    sky_fraction: float = 1.0
    """Fraction of open-sky irradiance this tile received on the last `step_day`.

    Diagnostics only; the value in force is the argument `step_day` was given.
    """

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
        sky_fraction: float = 1.0,
    ) -> LightResult:
        """Advance this tile by one day. Returns the resolved light climate.

        `sky_fraction` is the share of open-sky irradiance that reaches the top
        of this tile's canopy after its neighbours have taken their part -- see
        `ecocore.shading`. It defaults to 1.0, an unobstructed horizon, so a tile
        stepped on its own behaves exactly as it always has.
        """
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

        # 2. ONE light profile for every module in the tile, resolved against the
        #    irradiance this tile actually receives: open sky less whatever the
        #    neighbours' canopies block.
        profile = LightProfile(self.area_m2)
        for module in self.modules:
            profile.add(module.canopy_elements())
        self.sky_fraction = sky_fraction
        light = profile.resolve(day.par_umol_m2_s * sky_fraction)

        # Published for the neighbours' benefit. Read off the profile that was
        # just built, so it costs nothing beyond the max: asking the modules for
        # their canopy elements a second time would double the most expensive
        # call in the day.
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
            "x": self.x,
            "y": self.y,
            "soil_c": self.soil.total_c,
            "soil_n": self.soil.total_n,
            "mineral_n": self.soil.mineral_n,
            "soil_water_mm": self.soil.water_mm,
            "relative_water_content": self.soil.relative_water_content,
            "leached_n": self.soil.cumulative_leached_n,
            "canopy_top_m": self.canopy_top_m,
            "sky_view_fraction": self.sky_fraction,
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
