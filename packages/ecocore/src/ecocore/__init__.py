"""ecocore -- the coupling substrate shared by the forest and grassland models.

Contains no species biology. Its whole job is to guarantee that every tile has
exactly one vertical light profile and exactly one soil column, so `formind` and
`grassmind` compete for real resources instead of each simulating its own site.
"""

from .cohort import CanopyElement, Cohort
from .disturbance import Defoliation
from .dispersal import DispersalKernel, ExponentialKernel, NoDispersal, SeedRain
from .grid import Grid, SimulationResult, run_simulation
from .light import LightProfile, LightResult, compute_light
from .shading import LateralShading, NoLateralShading, SkyViewShading
from .soil import LitterInput, SoilColumn, SoilParameters
from .tile import StepContext, Tile, VegetationModule
from .weather import DayWeather, WeatherSeries, synthetic_weather

__all__ = [
    "CanopyElement",
    "Cohort",
    "DayWeather",
    "Defoliation",
    "DispersalKernel",
    "ExponentialKernel",
    "Grid",
    "LateralShading",
    "LightProfile",
    "LightResult",
    "LitterInput",
    "NoDispersal",
    "NoLateralShading",
    "SeedRain",
    "SimulationResult",
    "SkyViewShading",
    "SoilColumn",
    "SoilParameters",
    "StepContext",
    "Tile",
    "VegetationModule",
    "WeatherSeries",
    "compute_light",
    "run_simulation",
    "synthetic_weather",
]
