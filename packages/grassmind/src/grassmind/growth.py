"""Herbaceous carbon balance.

Structurally identical to `formind.growth` -- Michaelis-Menten leaf response,
analytically integrated over the plant's own leaf area, then respiration and
turnover subtracted. Sharing the functional form is not laziness: GRASSMIND
inherited it from FORMIND, so using two different photosynthesis formulations
here would make the coupled model less faithful, not more.

The difference from trees is entirely in the parameters (higher pmax, far higher
turnover, much larger root fraction) and in where the carbon goes afterwards.

Departures from the published formulation
-----------------------------------------

`nitrogen_limitation` scales MAINTENANCE RESPIRATION as well as GPP, exactly as
in `formind.growth` and for the same reason -- maintenance tracks tissue
nitrogen, so a starved sward pays less to hold what it has. GRASSMIND does model
nitrogen limitation, but as a growth-reduction factor on assimilation; applying
it there alone left upkeep unlimited and killed an unmanaged sward within ~12
years. This is this port's own choice, not a ported equation.

With `nitrogen_limitation` at 1.0 the carbon arithmetic is unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ecocore.units import SECONDS_PER_HOUR

from . import allometry

__all__ = ["CarbonBalance", "plant_photosynthesis", "daily_carbon_balance"]

KG_C_PER_UMOL_CO2 = 12.011e-9


@dataclass(frozen=True)
class CarbonBalance:
    """One day of carbon accounting for a single plant (kgC)."""

    gpp: float
    maintenance_respiration: float
    turnover_shoot: float
    turnover_root: float
    npp: float
    nitrogen_fixed: float


def plant_photosynthesis(incident_par: float, shoot_c: float, p) -> float:
    """Whole-plant gross assimilation (umol CO2 s-1)."""
    if incident_par <= 0.0 or shoot_c <= 0.0:
        return 0.0
    area = allometry.ground_area(shoot_c, p)
    if area <= 0.0:
        return 0.0
    m = p.leaf_transmittance
    numerator = p.alpha * p.k * incident_par + p.pmax * (1.0 - m)
    denominator = p.alpha * p.k * incident_par * math.exp(-p.k * p.plant_lai) + p.pmax * (1.0 - m)
    if denominator <= 0.0 or numerator <= 0.0:
        return 0.0
    return area * (p.pmax / p.k) * math.log(numerator / denominator)


def temperature_factor(temperature_c: float, optimum_c: float = 20.0, width_c: float = 13.0) -> float:
    """Bell-shaped temperature limitation, in [0, 1].

    Herbs have a lower optimum and a narrower window than trees, which is part of
    why grassland production peaks earlier in the season than forest production.
    """
    if temperature_c <= 0.0:
        return 0.0
    return math.exp(-(((temperature_c - optimum_c) / width_c) ** 2))


def daily_carbon_balance(
    shoot_c: float,
    root_c: float,
    incident_par: float,
    daylength_h: float,
    temperature_c: float,
    water_supply_fraction: float,
    nitrogen_limitation: float,
    p,
) -> CarbonBalance:
    """Full daily balance for one plant."""
    n_limit = max(0.0, min(1.0, nitrogen_limitation))
    assimilation = plant_photosynthesis(incident_par, shoot_c, p)
    gpp = (
        assimilation
        * daylength_h
        * SECONDS_PER_HOUR
        * KG_C_PER_UMOL_CO2
        * temperature_factor(temperature_c)
        * max(0.0, min(1.0, water_supply_fraction))
        * n_limit
    )

    living_c = shoot_c + root_c
    # Nitrogen limitation scales the WHOLE carbon economy, not just income.
    # Maintenance respiration is proportional to tissue nitrogen -- it is mostly
    # protein turnover and ion gradients -- so a stand that cannot get nitrogen
    # builds thinner, cheaper tissue and pays less to keep it. Applying the
    # limitation to GPP alone left maintenance at its unlimited value, and since
    # NPP is a small difference between the two, a ~20% cut in GPP became a
    # several-fold cut in NPP.
    maintenance = (
        p.maintenance_respiration
        * living_c
        * temperature_factor(temperature_c, 25.0, 18.0)
        * n_limit
    )
    turnover_shoot = shoot_c * p.shoot_turnover_per_year / 365.0
    turnover_root = root_c * p.root_turnover_per_year / 365.0

    net = gpp - maintenance
    npp = net * (1.0 - p.growth_respiration) if net > 0.0 else net

    # Legumes fix nitrogen in proportion to what they actually produce, and the
    # fixed nitrogen goes into the SHARED mineral pool -- see model.step_day.
    fixed = max(0.0, npp) * p.fixation_rate if p.nitrogen_fixing else 0.0

    return CarbonBalance(
        gpp=gpp,
        maintenance_respiration=maintenance,
        turnover_shoot=turnover_shoot,
        turnover_root=turnover_root,
        npp=npp,
        nitrogen_fixed=fixed,
    )
