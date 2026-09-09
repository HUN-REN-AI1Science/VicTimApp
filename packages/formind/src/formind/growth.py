"""Tree carbon balance: light -> GPP -> NPP -> diameter increment.

Photosynthesis follows FORMIND's analytic integration of a Michaelis-Menten leaf
response over the leaf area held inside a crown (FORMIND Handbook, "Tree
growth"). Integrating analytically rather than layer-by-layer is what lets a gap
model carry thousands of individuals cheaply, and it is the reason this port runs
a multi-decade tile in well under a second.

The incident irradiance on a crown is NOT computed here -- it arrives from
`ecocore.light`, already attenuated by every other tree AND by the grass sward
below. That is the coupling.

Departures from the published formulation
-----------------------------------------

Two, both introduced when nitrogen limitation was coupled in. The Handbook's
growth chapter has no nitrogen term at all -- FORMIND is light- and space-limited
-- so there is no published equation to follow here and these are this port's
own, recorded so the port stays auditable:

1. `nitrogen_limitation` scales MAINTENANCE RESPIRATION as well as GPP. The
   obvious reading -- limit assimilation only -- is wrong in a way that is easy
   to miss: maintenance is largely protein turnover and ion gradients, so it is
   proportional to tissue nitrogen, and a stand that cannot get nitrogen builds
   thinner, cheaper tissue and pays less to hold it. Leaving upkeep at its
   unlimited value while cutting income makes NPP, a small difference between two
   large terms, collapse several-fold for a ~20% cut in GPP.

2. `CarbonBalance` reports leaf and root turnover separately as well as summed.
   The Handbook needs only the total, because it tracks no nitrogen; this port
   needs the split because leaf and root litter differ several-fold in C:N and
   the caller charges each at its own ratio.

Neither changes the carbon arithmetic when `nitrogen_limitation` is 1.0, so an
uncoupled tree behaves exactly as the published equations describe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ecocore.units import DAYS_PER_YEAR, SECONDS_PER_HOUR

from . import allometry

__all__ = ["CarbonBalance", "crown_photosynthesis", "daily_carbon_balance"]

KG_C_PER_UMOL_CO2 = 12.011e-9
"""kg of carbon per umol of CO2 assimilated."""


@dataclass(frozen=True)
class CarbonBalance:
    """One day of carbon accounting for a single tree (kgC)."""

    gpp: float
    maintenance_respiration: float
    turnover_cost: float
    leaf_turnover_c: float
    """Leaf share of `turnover_cost` (kgC per tree per day)."""
    root_turnover_c: float
    """Root share of `turnover_cost`. Kept separate because leaf and root litter
    differ several-fold in C:N, and the stand must replace the nitrogen in both."""
    npp: float
    diameter_increment: float


def crown_photosynthesis(incident_par: float, dbh: float, p) -> float:
    """Whole-crown gross assimilation (umol CO2 s-1 per tree).

    Analytic integral of P(I) = alpha*I*pmax / (alpha*I + pmax) down through the
    crown's own leaf area, with Lambert-Beer attenuation inside the crown.
    """
    if incident_par <= 0.0 or dbh <= 0.0:
        return 0.0
    area = allometry.crown_area(dbh, p)
    if area <= 0.0:
        return 0.0

    m = p.leaf_transmittance
    k = p.k
    lai = p.crown_lai
    numerator = p.alpha * k * incident_par + p.pmax * (1.0 - m)
    denominator = p.alpha * k * incident_par * math.exp(-k * lai) + p.pmax * (1.0 - m)
    if denominator <= 0.0 or numerator <= 0.0:
        return 0.0
    return area * (p.pmax / k) * math.log(numerator / denominator)


def temperature_factor(temperature_c: float, optimum_c: float = 22.0, width_c: float = 14.0) -> float:
    """Bell-shaped temperature limitation of assimilation, in [0, 1]."""
    if temperature_c <= 0.0:
        return 0.0
    return math.exp(-(((temperature_c - optimum_c) / width_c) ** 2))


def daily_carbon_balance(
    dbh: float,
    incident_par: float,
    daylength_h: float,
    temperature_c: float,
    water_supply_fraction: float,
    nitrogen_limitation: float,
    p,
) -> CarbonBalance:
    """Full daily balance for one tree.

    `water_supply_fraction` and `nitrogen_limitation` both arrive from the shared
    soil column, so a grass sward that has drawn the column down measurably slows
    the trees above it.
    """
    n_limit = max(0.0, min(1.0, nitrogen_limitation))
    assimilation = crown_photosynthesis(incident_par, dbh, p)
    gpp = (
        assimilation
        * daylength_h
        * SECONDS_PER_HOUR
        * KG_C_PER_UMOL_CO2
        * temperature_factor(temperature_c)
        * max(0.0, min(1.0, water_supply_fraction))
        * n_limit
    )

    aboveground = allometry.aboveground_biomass_c(dbh, p)
    leaf_c = aboveground * p.leaf_fraction
    root_c = aboveground * p.root_fraction
    stem_c = aboveground - leaf_c

    # Only living tissue respires: leaves, roots and sapwood. Heartwood is dead,
    # so a veteran tree does not pay maintenance on centuries of accumulated
    # stem wood.
    living_c = leaf_c + root_c + stem_c * p.sapwood_fraction
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
    leaf_turnover = leaf_c * p.leaf_turnover_per_year / DAYS_PER_YEAR
    root_turnover = root_c * p.root_turnover_per_year / DAYS_PER_YEAR
    turnover = leaf_turnover + root_turnover

    net = gpp - maintenance - turnover
    npp = net * (1.0 - p.growth_respiration) if net > 0.0 else net

    if dbh >= p.max_dbh:
        increment = 0.0
    else:
        increment = allometry.diameter_increment(dbh, max(0.0, npp), p)

    return CarbonBalance(
        gpp=gpp,
        maintenance_respiration=maintenance,
        turnover_cost=turnover,
        leaf_turnover_c=leaf_turnover,
        root_turnover_c=root_turnover,
        npp=npp,
        diameter_increment=increment,
    )
