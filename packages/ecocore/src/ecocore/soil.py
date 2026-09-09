"""The shared soil column -- the coupling's second currency.

One column per tile. Both plant modules withdraw water and mineral nitrogen from
it and return litter to it, so a tree that dries the soil measurably limits the
grass beside it, and grass litter measurably feeds tree nutrition.

Structure follows CENTURY 4.0 (Parton et al.), which is the soil model GRASSMIND
3.0 itself recodes: two litter pools (structural / metabolic) and three soil
organic matter pools (active / slow / passive), each with a maximum decay rate
modified by temperature and moisture.

Carbon and nitrogen are conserved exactly. Every gram entering as litter either
sits in a pool, has been respired (tracked in `respired_c`), or has been taken up
by plants (tracked in `uptake_n`). `tests/test_soil.py` asserts the closing
balance to machine precision.

Departures from CENTURY 4.0
---------------------------

The pool structure, `MAX_DECAY_PER_YEAR`, `RESPIRATION_FRACTION` and `TARGET_CN`
are the published values and have deliberately been left alone -- they are what
makes this port auditable against Parton et al.

One addition: atmospheric nitrogen deposition (`add_deposition_n`). CENTURY
carries such an input; this port simply had not wired one, which left the only
nitrogen inputs litter recycling and legume fixation. It is tracked separately in
`cumulative_deposition_n` so it appears as its own term in the balance check.

One deliberate NON-change: `uptake_n` is uncapped. A soil-side diffusion limit on
what plants may withdraw per day was tried and removed -- at equilibrium it
cannot change the long-run mean supply, which is set by mineralisation, and the
larger standing mineral pool it leaves behind simply leaches more. Buffering
against a bad day belongs on the PLANT side; see each module's `_take_nitrogen`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .units import DAYS_PER_YEAR

__all__ = ["SoilParameters", "SoilColumn", "LitterInput"]

# CENTURY 4.0 maximum decay rates (per year), at optimal temperature and moisture.
MAX_DECAY_PER_YEAR = {
    "structural": 3.9,
    "metabolic": 14.8,
    "active": 7.3,
    "slow": 0.2,
    "passive": 0.0045,
}

# Fraction of decayed carbon respired as CO2 on each transfer (CENTURY 4.0).
RESPIRATION_FRACTION = {
    "structural_to_active": 0.45,
    "structural_to_slow": 0.30,
    "metabolic_to_active": 0.55,
    "active_to_slow": 0.55,
    "slow_to_active": 0.55,
    "slow_to_passive": 0.55,
    "passive_to_active": 0.55,
}

# Target C:N ratios of the receiving pools.
TARGET_CN = {"active": 8.0, "slow": 11.0, "passive": 11.0}


@dataclass(frozen=True)
class LitterInput:
    """One deposit of dead plant material.

    Both `formind` and `grassmind` emit these; the soil column does not care
    which growth form produced them, which is precisely the point.
    """

    carbon: float
    """kgC m-2."""
    nitrogen: float
    """kgN m-2."""
    lignin_fraction: float = 0.2
    """Lignin as a fraction of the deposited carbon."""


@dataclass
class SoilParameters:
    """Site properties. Defaults describe a loamy temperate soil."""

    depth_m: float = 1.0
    sand_fraction: float = 0.4
    clay_fraction: float = 0.2
    field_capacity_mm: float = 300.0
    wilting_point_mm: float = 120.0
    initial_active_c: float = 0.15
    initial_slow_c: float = 2.5
    initial_passive_c: float = 4.0
    initial_mineral_n: float = 0.004
    """kgN m-2, roughly 40 kg N ha-1."""
    nitrogen_deposition_kg_m2_year: float = 0.002
    """Atmospheric nitrogen deposition (kgN m-2 y-1), ~20 kgN ha-1 y-1.

    A typical Central European rate, and not a rounding error: it is comparable to
    the nitrogen a hay meadow exports in its crop. Omitting it leaves the model
    permanently nitrogen-starved, because resorption and microbial immobilisation
    together make the internal cycle tighter than the plants' demand.
    """
    leaching_efficiency: float = 0.25
    """Share of the mineral nitrogen in drained water that leaves the profile.

    Without leaching, mineral nitrogen accumulates without bound: mineralisation
    keeps adding to the pool and only plant uptake removes it, so a century-long
    run ends with implausible thousands of kg N per hectare. Leaching is the
    dominant real-world loss pathway and closes that budget.
    """

    def __post_init__(self) -> None:
        if self.field_capacity_mm <= self.wilting_point_mm:
            raise ValueError("field_capacity_mm must exceed wilting_point_mm")


@dataclass
class SoilColumn:
    """Carbon, nitrogen and water state of one tile's soil.

    All pool quantities are per square metre of ground, so they are directly
    comparable between tiles of different size.
    """

    params: SoilParameters = field(default_factory=SoilParameters)

    # Carbon pools (kgC m-2)
    structural_c: float = 0.0
    metabolic_c: float = 0.0
    active_c: float = 0.0
    slow_c: float = 0.0
    passive_c: float = 0.0

    # Nitrogen pools (kgN m-2)
    structural_n: float = 0.0
    metabolic_n: float = 0.0
    active_n: float = 0.0
    slow_n: float = 0.0
    passive_n: float = 0.0
    mineral_n: float = 0.0

    # Lignin carbon held in the structural pool (kgC m-2), for flow partitioning.
    structural_lignin_c: float = 0.0

    # Water (mm)
    water_mm: float = 0.0

    # Cumulative fluxes, for the conservation audit.
    respired_c: float = 0.0
    cumulative_litter_c: float = 0.0
    cumulative_litter_n: float = 0.0
    cumulative_uptake_n: float = 0.0
    cumulative_fertiliser_n: float = 0.0
    cumulative_fixed_n: float = 0.0
    cumulative_leached_n: float = 0.0
    cumulative_deposition_n: float = 0.0
    cumulative_drainage_mm: float = 0.0
    cumulative_evaporation_mm: float = 0.0
    cumulative_transpiration_mm: float = 0.0
    cumulative_precip_mm: float = 0.0

    def __post_init__(self) -> None:
        p = self.params
        if self.active_c == 0.0 and self.slow_c == 0.0 and self.passive_c == 0.0:
            self.active_c = p.initial_active_c
            self.slow_c = p.initial_slow_c
            self.passive_c = p.initial_passive_c
            self.active_n = self.active_c / TARGET_CN["active"]
            self.slow_n = self.slow_c / TARGET_CN["slow"]
            self.passive_n = self.passive_c / TARGET_CN["passive"]
            self.mineral_n = p.initial_mineral_n
        if self.water_mm == 0.0:
            self.water_mm = 0.5 * (p.field_capacity_mm + p.wilting_point_mm)

    # ---------------------------------------------------------------- water --

    @property
    def plant_available_water_mm(self) -> float:
        return max(0.0, self.water_mm - self.params.wilting_point_mm)

    @property
    def water_capacity_mm(self) -> float:
        return self.params.field_capacity_mm - self.params.wilting_point_mm

    @property
    def relative_water_content(self) -> float:
        """0 at wilting point, 1 at field capacity. Drives growth limitation."""
        return min(1.0, self.plant_available_water_mm / self.water_capacity_mm)

    def add_precipitation(self, precip_mm: float) -> float:
        """Add rainfall; return drainage lost below field capacity (mm).

        Drainage also carries dissolved mineral nitrogen out of the profile, in
        proportion to the share of the soil water that leaves.
        """
        self.cumulative_precip_mm += precip_mm
        self.water_mm += precip_mm
        drainage = max(0.0, self.water_mm - self.params.field_capacity_mm)
        if drainage > 0.0:
            total_water = self.water_mm
            leached = (
                self.mineral_n
                * (drainage / total_water)
                * self.params.leaching_efficiency
                if total_water > 0.0
                else 0.0
            )
            leached = min(leached, self.mineral_n)
            self.mineral_n -= leached
            self.cumulative_leached_n += leached
        self.water_mm -= drainage
        self.cumulative_drainage_mm += drainage
        return drainage

    def withdraw_water(self, demand_mm: float, transpiration: bool = True) -> float:
        """Remove water for transpiration or evaporation; return what was granted.

        Withdrawal cannot take the column below the wilting point, which is how
        drought limitation reaches the plant modules: they ask for what they need
        and receive what the shared column can actually supply.
        """
        granted = max(0.0, min(demand_mm, self.plant_available_water_mm))
        self.water_mm -= granted
        if transpiration:
            self.cumulative_transpiration_mm += granted
        else:
            self.cumulative_evaporation_mm += granted
        return granted

    # ------------------------------------------------------- litter and N ----

    def add_litter(self, litter: LitterInput) -> None:
        """Split a litter deposit into structural and metabolic pools.

        The metabolic fraction follows CENTURY's lignin-to-nitrogen rule: litter
        that is woody relative to its nitrogen content decomposes slowly.
        """
        if litter.carbon <= 0.0:
            return
        self.cumulative_litter_c += litter.carbon
        self.cumulative_litter_n += litter.nitrogen

        lignin_frac = min(0.5, max(0.0, litter.lignin_fraction))
        n_frac = litter.nitrogen / litter.carbon if litter.carbon > 0 else 0.0
        ln_ratio = lignin_frac / n_frac if n_frac > 1e-12 else 50.0
        metabolic_fraction = min(0.98, max(0.02, 0.85 - 0.018 * ln_ratio))

        met_c = litter.carbon * metabolic_fraction
        str_c = litter.carbon - met_c
        # Nitrogen follows carbon, but the metabolic pool is the N-rich one.
        met_n = min(litter.nitrogen, litter.nitrogen * metabolic_fraction * 1.5)
        str_n = litter.nitrogen - met_n

        self.metabolic_c += met_c
        self.metabolic_n += met_n
        self.structural_c += str_c
        self.structural_n += str_n
        self.structural_lignin_c += litter.carbon * lignin_frac * (str_c / litter.carbon)

    def uptake_n(self, demand: float) -> float:
        """Plant nitrogen uptake; returns what the shared mineral pool could supply.

        Uncapped: whatever mineralisation and deposition have put in the pool is
        available today. Buffering against a bad day happens on the PLANT side --
        see each module's `_take_nitrogen` -- because a soil-side cap throttles
        supply without changing the long-run mean, which is set by mineralisation.
        """
        granted = max(0.0, min(demand, self.mineral_n))
        self.mineral_n -= granted
        self.cumulative_uptake_n += granted
        return granted

    def add_fertiliser_n(self, amount: float) -> None:
        """Management input (grassmind.management). kgN m-2."""
        self.mineral_n += amount
        self.cumulative_fertiliser_n += amount

    def add_fixed_n(self, amount: float) -> None:
        """Biological nitrogen fixation by legumes (kgN m-2).

        Tracked separately from fertiliser because it is a genuinely new input to
        the site from the atmosphere, and because it is the channel through which
        a grassland process (legume fixation) fertilises the trees above it.
        """
        self.mineral_n += amount
        self.cumulative_fixed_n += amount

    # ------------------------------------------------------- decomposition --

    def decay_modifier(self, temperature_c: float) -> float:
        """Combined temperature and moisture rate modifier, in [0, 1]."""
        # CENTURY-style temperature response, peaking near 30 degC.
        t = 0.56 + (1.46 / math.pi) * math.atan(math.pi * 0.0309 * (temperature_c - 15.7))
        t = max(0.0, t)
        w = self.relative_water_content
        # Decomposition is suppressed when dry and mildly when saturated.
        moisture = max(0.0, min(1.0, 1.0 / (1.0 + 30.0 * math.exp(-8.5 * w))))
        return t * moisture

    def _transfer(self, donor: str, receiver: str, decayed_c: float, resp_key: str) -> None:
        """Move carbon and nitrogen from one pool to another, respiring the rest."""
        if decayed_c <= 0.0:
            return
        donor_c = getattr(self, f"{donor}_c")
        donor_n = getattr(self, f"{donor}_n")
        if donor_c <= 0.0:
            return
        decayed_n = decayed_c * (donor_n / donor_c)

        respired = decayed_c * RESPIRATION_FRACTION[resp_key]
        transferred_c = decayed_c - respired

        setattr(self, f"{donor}_c", donor_c - decayed_c)
        setattr(self, f"{donor}_n", donor_n - decayed_n)
        self.respired_c += respired

        required_n = transferred_c / TARGET_CN[receiver]
        if decayed_n >= required_n:
            # Net mineralisation: the surplus nitrogen becomes plant-available.
            self.mineral_n += decayed_n - required_n
            received_n = required_n
        else:
            # Immobilisation: draw the shortfall from the mineral pool if present.
            shortfall = required_n - decayed_n
            drawn = min(shortfall, self.mineral_n)
            self.mineral_n -= drawn
            received_n = decayed_n + drawn

        setattr(self, f"{receiver}_c", getattr(self, f"{receiver}_c") + transferred_c)
        setattr(self, f"{receiver}_n", getattr(self, f"{receiver}_n") + received_n)

    def add_deposition_n(self, days: float = 1.0) -> None:
        """Atmospheric nitrogen input for `days` (kgN m-2)."""
        amount = self.params.nitrogen_deposition_kg_m2_year * days / DAYS_PER_YEAR
        self.mineral_n += amount
        self.cumulative_deposition_n += amount

    def decompose(self, temperature_c: float, days: float = 1.0) -> None:
        """Advance decomposition by `days`."""
        modifier = self.decay_modifier(temperature_c)
        if modifier <= 0.0:
            return
        dt = days / DAYS_PER_YEAR

        def rate(pool: str) -> float:
            return MAX_DECAY_PER_YEAR[pool] * modifier * dt

        # Structural litter splits by its lignin content: lignin goes to slow.
        if self.structural_c > 0.0:
            decayed = min(self.structural_c, self.structural_c * rate("structural"))
            lignin_share = min(0.9, self.structural_lignin_c / self.structural_c)
            self.structural_lignin_c = max(
                0.0, self.structural_lignin_c - decayed * lignin_share
            )
            self._transfer("structural", "slow", decayed * lignin_share, "structural_to_slow")
            self._transfer(
                "structural", "active", decayed * (1.0 - lignin_share), "structural_to_active"
            )

        if self.metabolic_c > 0.0:
            decayed = min(self.metabolic_c, self.metabolic_c * rate("metabolic"))
            self._transfer("metabolic", "active", decayed, "metabolic_to_active")

        if self.active_c > 0.0:
            decayed = min(self.active_c, self.active_c * rate("active"))
            # Texture controls how much active carbon is stabilised into slow SOM.
            to_passive = decayed * 0.004
            self._transfer("active", "passive", to_passive, "slow_to_passive")
            self._transfer("active", "slow", decayed - to_passive, "active_to_slow")

        if self.slow_c > 0.0:
            decayed = min(self.slow_c, self.slow_c * rate("slow"))
            to_passive = decayed * 0.03
            self._transfer("slow", "passive", to_passive, "slow_to_passive")
            self._transfer("slow", "active", decayed - to_passive, "slow_to_active")

        if self.passive_c > 0.0:
            decayed = min(self.passive_c, self.passive_c * rate("passive"))
            self._transfer("passive", "active", decayed, "passive_to_active")

    # ------------------------------------------------------------ audit -----

    @property
    def total_c(self) -> float:
        return self.structural_c + self.metabolic_c + self.active_c + self.slow_c + self.passive_c

    @property
    def total_n(self) -> float:
        return (
            self.structural_n
            + self.metabolic_n
            + self.active_n
            + self.slow_n
            + self.passive_n
            + self.mineral_n
        )

    def carbon_balance_error(self, initial_total_c: float) -> float:
        """Should be ~0. Positive means carbon appeared from nowhere."""
        return self.total_c + self.respired_c - initial_total_c - self.cumulative_litter_c

    def nitrogen_balance_error(self, initial_total_n: float) -> float:
        """Should be ~0."""
        return (
            self.total_n
            + self.cumulative_uptake_n
            + self.cumulative_leached_n
            - initial_total_n
            - self.cumulative_litter_n
            - self.cumulative_fertiliser_n
            - self.cumulative_fixed_n
            - self.cumulative_deposition_n
        )
