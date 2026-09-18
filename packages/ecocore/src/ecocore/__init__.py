"""ecocore -- the coupling substrate shared by the forest and grassland models.

Contains no species biology. Its whole job is to guarantee that every tile has
exactly one vertical light profile and exactly one soil column, so `formind` and
`grassmind` compete for real resources instead of each simulating its own site.
"""

from .cohort import CanopyElement, Cohort
from .disturbance import Defoliation
from .light import LightProfile, LightResult, compute_light
from .simulation import SimulationResult, run_simulation
from .soil import LitterInput, SoilColumn, SoilParameters
from .tile import SeedRain, StepContext, Tile, VegetationModule
from .weather import DayWeather, WeatherSeries, synthetic_weather

__all__ = [
    "CanopyElement",
    "Cohort",
    "DayWeather",
    "Defoliation",
    "LightProfile",
    "LightResult",
    "LitterInput",
    "SeedRain",
    "SimulationResult",
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
