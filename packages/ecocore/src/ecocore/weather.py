"""Daily climate drivers, shared by every tile in a run.

Both plant modules read the same day record, so seasonality is automatically
synchronised between forest and grassland -- there is no way for the two to
drift onto different calendars.

The synthetic generator exists so the whole model chain runs offline with no
external data. Real runs should load ERA5/Copernicus series through
`WeatherSeries.from_arrays`, which is the same interface GRASSMIND's BioDT
deployment uses (`general-copernicus-weather-data`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .units import (
    DAYS_PER_YEAR,
    PAR_FRACTION_OF_SHORTWAVE,
    SECONDS_PER_HOUR,
    UMOL_PHOTONS_PER_J_PAR,
)

__all__ = ["DayWeather", "WeatherSeries", "synthetic_weather"]


@dataclass(frozen=True)
class DayWeather:
    """One day of drivers."""

    day_of_year: int
    temperature_c: float
    precipitation_mm: float
    radiation_mj_m2: float
    """Incoming shortwave radiation (MJ m-2 d-1)."""
    daylength_h: float

    @property
    def par_umol_m2_s(self) -> float:
        """Mean PAR photon flux density during daylight (umol m-2 s-1).

        Converts daily shortwave energy to a daylight-averaged photon flux, which
        is the quantity the Michaelis-Menten light-response curves expect.
        """
        if self.daylength_h <= 0.0:
            return 0.0
        par_joules = self.radiation_mj_m2 * 1e6 * PAR_FRACTION_OF_SHORTWAVE
        return par_joules * UMOL_PHOTONS_PER_J_PAR / (self.daylength_h * SECONDS_PER_HOUR)

    @property
    def potential_evapotranspiration_mm(self) -> float:
        """Priestley-Taylor style PET (mm d-1), temperature and radiation driven."""
        if self.temperature_c <= 0.0:
            return 0.0
        # Slope of the saturation vapour pressure curve over (slope + gamma).
        s = 4098.0 * (0.6108 * math.exp(17.27 * self.temperature_c / (self.temperature_c + 237.3)))
        s /= (self.temperature_c + 237.3) ** 2
        gamma = 0.066
        alpha = 1.26
        latent_heat = 2.45  # MJ kg-1
        return max(0.0, alpha * (s / (s + gamma)) * self.radiation_mj_m2 / latent_heat)


class WeatherSeries:
    """A finite series of daily drivers, cycled if the run outlasts it."""

    def __init__(
        self,
        temperature_c: np.ndarray,
        precipitation_mm: np.ndarray,
        radiation_mj_m2: np.ndarray,
        latitude_deg: float = 51.0,
        start_day_of_year: int = 1,
    ) -> None:
        lengths = {len(temperature_c), len(precipitation_mm), len(radiation_mj_m2)}
        if len(lengths) != 1:
            raise ValueError("weather arrays must have equal length")
        if lengths == {0}:
            raise ValueError("weather series is empty")
        self.temperature_c = np.asarray(temperature_c, dtype=float)
        self.precipitation_mm = np.asarray(precipitation_mm, dtype=float)
        self.radiation_mj_m2 = np.asarray(radiation_mj_m2, dtype=float)
        self.latitude_deg = latitude_deg
        self.start_day_of_year = start_day_of_year

    @classmethod
    def from_arrays(cls, **kwargs) -> "WeatherSeries":
        return cls(**kwargs)

    def __len__(self) -> int:
        return len(self.temperature_c)

    def day(self, step: int) -> DayWeather:
        """Driver record for simulation day `step` (0-based), cycling the series."""
        i = step % len(self)
        doy = (self.start_day_of_year - 1 + step) % DAYS_PER_YEAR + 1
        return DayWeather(
            day_of_year=doy,
            temperature_c=float(self.temperature_c[i]),
            precipitation_mm=float(self.precipitation_mm[i]),
            radiation_mj_m2=float(self.radiation_mj_m2[i]),
            daylength_h=daylength_hours(self.latitude_deg, doy),
        )


def daylength_hours(latitude_deg: float, day_of_year: int) -> float:
    """Astronomical daylength (h). Standard solar declination formula."""
    lat = math.radians(max(-66.0, min(66.0, latitude_deg)))
    declination = 0.409 * math.sin(2.0 * math.pi * day_of_year / DAYS_PER_YEAR - 1.39)
    cos_hour_angle = -math.tan(lat) * math.tan(declination)
    cos_hour_angle = max(-1.0, min(1.0, cos_hour_angle))
    return 24.0 * math.acos(cos_hour_angle) / math.pi


def synthetic_weather(
    years: int = 1,
    latitude_deg: float = 51.0,
    mean_temperature_c: float = 9.0,
    temperature_amplitude_c: float = 9.0,
    annual_precipitation_mm: float = 700.0,
    peak_radiation_mj_m2: float = 22.0,
    seed: int = 0,
) -> WeatherSeries:
    """A reproducible temperate-Europe climate, good enough to exercise the model.

    Defaults approximate a Central German grassland site of the kind GRASSMIND is
    parameterised for.
    """
    rng = np.random.default_rng(seed)
    n = years * DAYS_PER_YEAR
    doy = np.arange(n) % DAYS_PER_YEAR + 1
    phase = 2.0 * math.pi * (doy - 15) / DAYS_PER_YEAR

    temperature = mean_temperature_c - temperature_amplitude_c * np.cos(phase)
    temperature += rng.normal(0.0, 2.0, n)

    radiation = 0.5 * peak_radiation_mj_m2 * (1.0 - np.cos(phase)) + 2.0
    radiation *= rng.uniform(0.55, 1.0, n)

    wet = rng.random(n) < 0.33
    precipitation = np.where(wet, rng.gamma(1.4, 6.0, n), 0.0)
    scale = annual_precipitation_mm * years / max(precipitation.sum(), 1e-9)
    precipitation *= scale

    return WeatherSeries(temperature, precipitation, radiation, latitude_deg)
