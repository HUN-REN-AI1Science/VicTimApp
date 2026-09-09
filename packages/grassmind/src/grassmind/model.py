"""The grassland vegetation module -- GRASSMIND's process chain behind ecocore's contract.

`GrasslandModule` is a `ecocore.tile.VegetationModule`. Like `formind.ForestModule`
it cannot see the other model. Trees reach it only as less light at its leaves
and less water in the shared column; it reaches the trees only by drawing that
column down, by shading the forest floor where seedlings would establish, and --
for legumes -- by fixing nitrogen the trees can then take up.

Departures from the published formulation
-----------------------------------------

GRASSMIND does model nitrogen limitation, but the three details below are this
port's own and are recorded here so the port stays auditable:

1. **A plant nitrogen reserve** (`N_RESERVE_DAYS`, `_take_nitrogen`), as in
   `formind.model`. For a sward the reserve changes WHEN a shortfall bites rather
   than whether it does, but that timing matters: without it the deepest cut
   landed on the most productive days. INVENTED BY THIS PORT and load-bearing --
   see `validation/README.md`.

2. **Litter nitrogen charged per tissue** -- shoot at `cn_ratio`, root at
   `root_cn_ratio`. Roots are the larger flux and much the poorer in nitrogen, so
   a single shoot ratio overstated the nitrogen leaving in litter.

3. **Growth demand uses an allocation-weighted C:N** (`_mean_growth_cn_ratio`)
   rather than the shoot ratio. `root_fraction` is ~0.62, so most new carbon
   becomes root; sizing demand on shoot tissue alone overstated it.

Grazing also returns nitrogen at `nitrogen_return_fraction` rather than at the
carbon `return_fraction` -- see `management.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ecocore.cohort import CanopyElement, Cohort
from ecocore.disturbance import Defoliation
from ecocore.soil import LitterInput
from ecocore.tile import StepContext
from ecocore.weather import DayWeather

from . import allometry, mortality, recruitment
from .growth import daily_carbon_balance
from .management import ManagementSchedule
from .pft import DEFAULT_GRASS_PFTS, GrassPFT

__all__ = ["GrassCohort", "GrasslandModule"]

MERGE_SHOOT_BINS = 40
"""Number of logarithmic shoot-mass classes used when merging cohorts."""


@dataclass
class GrassCohort(Cohort):
    """A group of identical herbaceous plants. State is shoot and root carbon."""

    shoot_c: float = 0.0
    light_fraction: float = 1.0
    """Irradiance at this cohort's leaves / incident, carried from the last day.

    Read by `mortality.annual_mortality_rate`, which is how a closing tree canopy
    turns into grassland death rather than merely slower grassland growth.
    """

    def sync_biomass(self, p: GrassPFT) -> None:
        self.leaf_c = self.shoot_c * p.leaf_fraction_of_shoot
        self.stem_c = self.shoot_c - self.leaf_c


N_RESERVE_DAYS = 60.0
"""Days of nitrogen demand a sward can carry internally. See `_take_nitrogen`.

NOT a ported parameter -- see the module docstring, "Departures". Load-bearing:
at 90 days an abandoned tile is never invaded by trees at all.
"""


@dataclass
class GrasslandModule:
    """GRASSMIND process chain for one tile."""

    pfts: list[GrassPFT] = field(default_factory=lambda: list(DEFAULT_GRASS_PFTS))
    cohorts: list[GrassCohort] = field(default_factory=list)
    management: ManagementSchedule = field(default_factory=ManagementSchedule)
    name: str = "grassland"

    # Diagnostics
    annual_gpp: float = 0.0
    annual_npp: float = 0.0
    last_annual_gpp: float = 0.0
    last_annual_npp: float = 0.0
    annual_harvest_c: float = 0.0
    last_harvest_c: float = 0.0
    last_annual_fixed_n: float = 0.0
    _last_gpp: float = 0.0
    _last_npp: float = 0.0
    _n_limitation: float = 1.0
    _n_reserve: float = 0.0
    """Plant-held nitrogen buffer (kgN m-2). See `_take_nitrogen`."""
    _annual_fixed_n: float = 0.0
    _last_fixed_n: float = 0.0
    exported_c: float = 0.0
    exported_n: float = 0.0
    _clonal_pool: dict = field(default_factory=dict)
    """Carbon set aside for clonal offspring, per PFT (kgC per tile)."""

    def __post_init__(self) -> None:
        self._pft_by_id = {p.id: p for p in self.pfts}
        for cohort in self.cohorts:
            cohort.sync_biomass(self._pft_by_id[cohort.pft])

    # ------------------------------------------------------------- setup ----

    @classmethod
    def sown_sward(
        cls,
        pfts: list[GrassPFT] | None = None,
        plants_per_m2: float = 300.0,
        management: ManagementSchedule | None = None,
        tile_area_m2: float = 400.0,
    ) -> "GrasslandModule":
        """An established sward, evenly split between the functional groups."""
        pfts = list(pfts or DEFAULT_GRASS_PFTS)
        module = cls(pfts=pfts, management=management or ManagementSchedule())
        share = plants_per_m2 * tile_area_m2 / len(pfts)
        for p in pfts:
            cohort = GrassCohort(pft=p.id, n=share, shoot_c=p.initial_shoot_c * 5.0)
            cohort.root_c = cohort.shoot_c * p.root_fraction / (1.0 - p.root_fraction)
            cohort.sync_biomass(p)
            module.cohorts.append(cohort)
        return module

    @classmethod
    def bare_ground(
        cls, pfts: list[GrassPFT] | None = None, management: ManagementSchedule | None = None
    ) -> "GrasslandModule":
        return cls(pfts=list(pfts or DEFAULT_GRASS_PFTS), management=management or ManagementSchedule())

    def pft(self, pft_id: str) -> GrassPFT:
        return self._pft_by_id[pft_id]

    # -------------------------------------------------- ecocore contract ----

    def canopy_elements(self) -> list[CanopyElement]:
        elements = []
        for cohort in self.cohorts:
            if cohort.n <= 0.0 or cohort.shoot_c <= 0.0:
                continue
            p = self._pft_by_id[cohort.pft]
            top = allometry.height(cohort.shoot_c, p)
            if top <= 0.0:
                continue
            elements.append(
                CanopyElement(
                    key=id(cohort),
                    base_m=0.0,
                    top_m=top,
                    leaf_area_m2=allometry.leaf_area(cohort.shoot_c, p) * cohort.n,
                    k=p.k,
                )
            )
        return elements

    def emit_disturbances(self, day: DayWeather) -> list[Defoliation]:
        """Turn today's management actions into tile-level events.

        Emitting rather than applying them directly is what lets the forest
        module see the same mowing that the grass sees.
        """
        events: list[Defoliation] = []
        mow = self.management.mowing_today(day.day_of_year)
        if mow is not None:
            events.append(
                Defoliation(
                    source="mowing",
                    cut_height_m=mow.cut_height_m,
                    removal_fraction=mow.removal_fraction,
                    woody_kill_height_m=mow.woody_kill_height_m,
                    woody_kill_fraction=1.0,
                )
            )
        graze = self.management.grazing_today(day.day_of_year)
        if graze is not None:
            events.append(
                Defoliation(
                    source="grazing",
                    cut_height_m=graze.min_height_m,
                    removal_fraction=1.0 - graze.return_fraction,
                    nitrogen_removal_fraction=1.0 - graze.nitrogen_return_fraction,
                    woody_kill_height_m=graze.woody_kill_height_m,
                    woody_kill_fraction=graze.woody_kill_fraction,
                )
            )
        return events

    def water_demand_mm(self, day: DayWeather, light) -> float:
        if light.incident_par <= 0.0:
            return 0.0
        keys = {id(c) for c in self.cohorts}
        absorbed = sum(v for k, v in light.absorbed_par.items() if k in keys)
        return day.potential_evapotranspiration_mm * absorbed / light.incident_par

    def step_day(self, ctx: StepContext) -> None:
        gpp_total = 0.0
        npp_total = 0.0
        litter_c = 0.0
        litter_n = 0.0
        fixed_n = 0.0

        for cohort in self.cohorts:
            if cohort.n <= 0.0:
                continue
            p = self._pft_by_id[cohort.pft]
            incident = ctx.light.mean_incident_par.get(id(cohort), 0.0)
            cohort.light_fraction = (
                incident / ctx.light.incident_par if ctx.light.incident_par > 0.0 else 1.0
            )

            balance = daily_carbon_balance(
                shoot_c=cohort.shoot_c,
                root_c=cohort.root_c,
                incident_par=incident,
                daylength_h=ctx.day.daylength_h,
                temperature_c=ctx.day.temperature_c,
                water_supply_fraction=ctx.water_supply_fraction,
                nitrogen_limitation=self._n_limitation,
                p=p,
            )

            gpp_total += balance.gpp * cohort.n
            npp_total += balance.npp * cohort.n
            fixed_n += balance.nitrogen_fixed * cohort.n

            # Allocation, then turnover, both per plant.
            if balance.npp > 0.0:
                cohort.shoot_c += balance.npp * (1.0 - p.root_fraction)
                cohort.root_c += balance.npp * p.root_fraction
            else:
                # A carbon deficit is paid out of standing biomass.
                deficit = -balance.npp
                total = cohort.shoot_c + cohort.root_c
                if total > 0.0:
                    cohort.shoot_c = max(0.0, cohort.shoot_c - deficit * cohort.shoot_c / total)
                    cohort.root_c = max(0.0, cohort.root_c - deficit * cohort.root_c / total)

            # Regrowth from reserves: refill the shoot toward its target share
            # of the plant. This is what lets a mown sward come back.
            total_c = cohort.shoot_c + cohort.root_c
            target_shoot = total_c * (1.0 - p.root_fraction)
            if cohort.shoot_c < target_shoot and cohort.root_c > 0.0:
                moved = min(
                    cohort.root_c * 0.5,
                    (target_shoot - cohort.shoot_c) * p.remobilisation_rate,
                )
                cohort.shoot_c += moved
                cohort.root_c -= moved

            # Tillering: an individual that has reached its maximum size puts
            # surplus growth into clonal offspring instead of getting larger.
            if cohort.shoot_c > p.max_shoot_c:
                surplus = cohort.shoot_c - p.max_shoot_c
                cohort.shoot_c = p.max_shoot_c
                self._clonal_pool[p.id] = self._clonal_pool.get(p.id, 0.0) + surplus * cohort.n

            shed_shoot = min(cohort.shoot_c, balance.turnover_shoot)
            shed_root = min(cohort.root_c, balance.turnover_root)
            cohort.shoot_c -= shed_shoot
            cohort.root_c -= shed_root
            shed = (shed_shoot + shed_root) * cohort.n
            litter_c += shed
            # Resorbed before senescence and reused, so litter is nitrogen-poorer
            # than the living tissue. Shoot and root are charged at their OWN C:N:
            # roots are the larger flux and much the poorer in nitrogen, so a
            # single shoot ratio for both overstates the nitrogen leaving.
            litter_n += (
                shed_shoot / p.cn_ratio + shed_root / p.root_cn_ratio
            ) * cohort.n * (1.0 - p.nitrogen_resorption)

            cohort.sync_biomass(p)
            cohort.age_days += 1

        # Management acts on standing biomass, after growth, before litter goes in.
        harvest_c, harvest_n, management_litter_c, management_litter_n = self._apply_management(ctx)
        litter_c += management_litter_c
        litter_n += management_litter_n

        if litter_c > 0.0:
            ctx.soil.add_litter(
                LitterInput(
                    carbon=litter_c / ctx.tile_area_m2,
                    nitrogen=litter_n / ctx.tile_area_m2,
                    lignin_fraction=0.12,
                )
            )

        if fixed_n > 0.0:
            # Straight into the SHARED mineral pool: the trees can take it up too.
            ctx.soil.add_fixed_n(fixed_n / ctx.tile_area_m2)

        # Demand covers new tissue AND replacement of the nitrogen leaving in
        # shed and harvested material, at the same C:N the tissue is built to.
        # Sizing it on new growth alone makes the sward a net nitrogen source.
        growth_demand = max(0.0, npp_total) / self._mean_growth_cn_ratio()
        demand = (growth_demand + litter_n + harvest_n) / ctx.tile_area_m2
        self._n_limitation = self._take_nitrogen(ctx, demand)

        self._last_gpp = gpp_total / ctx.tile_area_m2
        self._last_npp = npp_total / ctx.tile_area_m2
        self._last_fixed_n = fixed_n / ctx.tile_area_m2
        self.annual_gpp += self._last_gpp
        self.annual_npp += self._last_npp
        self._annual_fixed_n += self._last_fixed_n
        self.annual_harvest_c += harvest_c / ctx.tile_area_m2
        self.exported_c += harvest_c / ctx.tile_area_m2
        self.exported_n += harvest_n / ctx.tile_area_m2

    def step_year(self, ctx: StepContext) -> None:
        self._apply_mortality(ctx)
        self._apply_density_limitation(ctx)
        self._offer_seeds(ctx)
        self._establish(ctx)
        self._tiller(ctx)
        self.cohorts = [c for c in self.cohorts if c.n > 1e-6 and c.shoot_c > 0.0]
        self._merge_cohorts()
        self.last_harvest_c = self.annual_harvest_c
        self.annual_harvest_c = 0.0
        self.last_annual_fixed_n = self._annual_fixed_n
        self.last_annual_gpp = self.annual_gpp
        self.last_annual_npp = self.annual_npp
        self.annual_gpp = 0.0
        self.annual_npp = 0.0
        self._annual_fixed_n = 0.0

    # ------------------------------------------------------- management -----

    def _apply_management(self, ctx: StepContext) -> tuple[float, float, float, float]:
        """Apply today's tile events to the sward.

        Reads `ctx.disturbances` rather than the schedule directly, so grass and
        trees respond to one and the same event. Fertilisation stays here because
        it acts on the soil, not on standing biomass.

        Returns (harvest_c, harvest_n, litter_c, litter_n), all per tile.
        """
        harvest_c = harvest_n = litter_c = litter_n = 0.0

        fertiliser = self.management.fertilisation_today(ctx.day.day_of_year)
        if fertiliser > 0.0:
            ctx.soil.add_fertiliser_n(fertiliser)

        for event in ctx.disturbances:
            for cohort in self.cohorts:
                p = self._pft_by_id[cohort.pft]
                standing_height = allometry.height(cohort.shoot_c, p)
                if standing_height <= event.cut_height_m:
                    continue
                if event.source == "grazing":
                    # Continuous intake, not a clean cut.
                    removed_per_plant = cohort.shoot_c * self._grazing_intake(ctx)
                else:
                    remaining = min(
                        cohort.shoot_c, allometry.shoot_from_height(event.cut_height_m, p)
                    )
                    removed_per_plant = cohort.shoot_c - remaining
                if removed_per_plant <= 0.0:
                    continue
                cohort.shoot_c -= removed_per_plant
                cohort.sync_biomass(p)
                removed = removed_per_plant * cohort.n
                harvest_c += removed * event.removal_fraction
                harvest_n += removed * event.n_removal_fraction / p.cn_ratio
                litter_c += removed * (1.0 - event.removal_fraction)
                litter_n += removed * (1.0 - event.n_removal_fraction) / p.cn_ratio

        return harvest_c, harvest_n, litter_c, litter_n

    def _take_nitrogen(self, ctx: StepContext, demand: float) -> float:
        """Draw `demand` (kgN m-2) from the shared pool; return tomorrow's limitation.

        The sward buffers nitrogen internally -- in roots and stem bases, the same
        reserve that regrows a shoot after a cut -- and remobilises it when daily
        uptake falls short, so the module carries `N_RESERVE_DAYS` of demand.

        Without the reserve the limitation was a single day's `granted / demand`.
        Demand peaks exactly when growth peaks, so the deepest cut landed on the
        most productive days; since NPP is a small difference between GPP and
        respiration, a ~20% mean cut in GPP collapsed NPP several-fold and the
        sward bled out even unmanaged. Nitrogen is still genuinely limiting here --
        the reserve changes WHEN the shortfall bites, not whether it does.
        """
        if demand <= 0.0:
            return 1.0
        capacity = demand * N_RESERVE_DAYS
        granted = ctx.soil.uptake_n(demand + max(0.0, capacity - self._n_reserve))
        if granted >= demand:
            self._n_reserve = min(capacity, self._n_reserve + granted - demand)
            return 1.0
        drawn = min(demand - granted, self._n_reserve)
        self._n_reserve -= drawn
        return (granted + drawn) / demand

    def _mean_growth_cn_ratio(self) -> float:
        """C:N of the tissue this NPP actually builds, weighted by allocation.

        `root_fraction` sends most of NPP below ground, where tissue is far poorer
        in nitrogen, so sizing growth demand on the shoot ratio alone charged the
        sward roughly a quarter more nitrogen than it needed.
        """
        total = sum(c.shoot_c * c.n for c in self.cohorts)
        if total <= 0.0:
            p = self.pfts[0]
            return 1.0 / ((1.0 - p.root_fraction) / p.cn_ratio + p.root_fraction / p.root_cn_ratio)
        weight = 0.0
        for c in self.cohorts:
            p = self._pft_by_id[c.pft]
            per_kg = (1.0 - p.root_fraction) / p.cn_ratio + p.root_fraction / p.root_cn_ratio
            weight += c.shoot_c * c.n * per_kg
        return total / weight

    def _grazing_intake(self, ctx: StepContext) -> float:
        period = self.management.grazing_today(ctx.day.day_of_year)
        return period.intake_fraction_per_day if period is not None else 0.0

    # ----------------------------------------------------------- internals --

    def _return_to_soil(self, ctx: StepContext, cohort: GrassCohort, dead: float) -> None:
        p = self._pft_by_id[cohort.pft]
        carbon = (cohort.shoot_c + cohort.root_c) * dead
        if carbon <= 0.0:
            return
        ctx.soil.add_litter(
            LitterInput(
                carbon=carbon / ctx.tile_area_m2,
                nitrogen=carbon / p.cn_ratio / ctx.tile_area_m2,
                lignin_fraction=p.lignin_fraction,
            )
        )

    def _apply_mortality(self, ctx: StepContext) -> None:
        for cohort in self.cohorts:
            p = self._pft_by_id[cohort.pft]
            rate = mortality.annual_mortality_rate(cohort.light_fraction, p)
            dead = cohort.n * rate
            if dead > 0.0:
                self._return_to_soil(ctx, cohort, dead)
                cohort.n -= dead

    def _apply_density_limitation(self, ctx: StepContext) -> None:
        for p in self.pfts:
            members = [c for c in self.cohorts if c.pft == p.id and c.n > 0.0]
            density = sum(c.n for c in members) / ctx.tile_area_m2
            fraction = mortality.density_excess_fraction(density, p)
            if fraction <= 0.0:
                continue
            for cohort in sorted(members, key=lambda c: c.shoot_c):
                dead = cohort.n * fraction
                self._return_to_soil(ctx, cohort, dead)
                cohort.n -= dead

    def _offer_seeds(self, ctx: StepContext) -> None:
        for p in self.pfts:
            standing = sum(c.n * c.shoot_c for c in self.cohorts if c.pft == p.id)
            if standing <= 0.0:
                continue
            # Seed output saturates with standing biomass.
            intensity = min(1.0, standing / (0.05 * ctx.tile_area_m2))
            ctx.seed_rain.offer(p.id, p.seeds_per_m2_year * intensity)

    def _establish(self, ctx: StepContext) -> None:
        floor_fraction = (
            ctx.light.floor_par / ctx.light.incident_par if ctx.light.incident_par > 0 else 1.0
        )
        for p in self.pfts:
            density = (
                sum(c.n for c in self.cohorts if c.pft == p.id) / ctx.tile_area_m2
            )
            n_new = recruitment.establishment_number(
                ctx.seed_rain.available(p.id), floor_fraction, ctx.tile_area_m2, density, p
            )
            if n_new < 1.0:
                continue
            cohort = GrassCohort(pft=p.id, n=n_new, shoot_c=p.initial_shoot_c)
            cohort.root_c = cohort.shoot_c * p.root_fraction / (1.0 - p.root_fraction)
            cohort.sync_biomass(p)
            self.cohorts.append(cohort)

    def _tiller(self, ctx: StepContext) -> None:
        """Turn the clonal pool into new individuals.

        Clonal offspring, unlike seedlings, are provisioned by the parent, so
        they start at the sward's establishment size with a full root share and
        are not gated on floor light -- a tiller emerges beside its parent, in
        the parent's own light environment. Carbon that cannot be placed because
        the sward is at maximum density is returned to the soil as litter.
        """
        for p in self.pfts:
            pool = self._clonal_pool.get(p.id, 0.0)
            if pool <= 0.0:
                continue
            self._clonal_pool[p.id] = 0.0
            cost = p.initial_shoot_c * 4.0 / (1.0 - p.root_fraction)
            density = sum(c.n for c in self.cohorts if c.pft == p.id) / ctx.tile_area_m2
            room = max(0.0, p.max_density_per_m2 - density) * ctx.tile_area_m2
            n_new = min(pool / cost, room)
            if n_new >= 1.0:
                shoot = p.initial_shoot_c * 4.0
                cohort = GrassCohort(pft=p.id, n=n_new, shoot_c=shoot)
                cohort.root_c = shoot * p.root_fraction / (1.0 - p.root_fraction)
                cohort.sync_biomass(p)
                self.cohorts.append(cohort)
                pool -= n_new * cost
            if pool > 0.0:
                ctx.soil.add_litter(
                    LitterInput(
                        carbon=pool / ctx.tile_area_m2,
                        nitrogen=pool / p.cn_ratio / ctx.tile_area_m2,
                        lignin_fraction=p.lignin_fraction,
                    )
                )

    def _merge_cohorts(self) -> None:
        """Collapse cohorts of the same PFT in the same shoot-mass class.

        Same purpose as `formind.ForestModule._merge_cohorts`: without it, annual
        recruitment grows the cohort list without bound. Classes are logarithmic
        because herbaceous plant mass spans several orders of magnitude between a
        seedling and a mature tussock.
        """
        import math

        if len(self.cohorts) < 2:
            return
        buckets: dict[tuple[str, int], GrassCohort] = {}
        merged: list[GrassCohort] = []
        for cohort in self.cohorts:
            decade = int(math.log10(max(cohort.shoot_c, 1e-12)) * 8.0)
            key = (cohort.pft, decade)
            existing = buckets.get(key)
            if existing is None:
                buckets[key] = cohort
                merged.append(cohort)
                continue
            total = existing.n + cohort.n
            if total <= 0.0:
                continue
            existing.shoot_c = (existing.shoot_c * existing.n + cohort.shoot_c * cohort.n) / total
            existing.root_c = (existing.root_c * existing.n + cohort.root_c * cohort.n) / total
            existing.light_fraction = (
                existing.light_fraction * existing.n + cohort.light_fraction * cohort.n
            ) / total
            existing.n = total
            existing.sync_biomass(self._pft_by_id[existing.pft])
        self.cohorts = merged

    # -------------------------------------------------------- diagnostics ---

    def diagnostics(self, area_m2: float) -> dict:
        """Sward state, all per m2 of ground. See `ecocore.tile.VegetationModule`."""
        shoot = sum(c.shoot_c * c.n for c in self.cohorts)
        root = sum(c.root_c * c.n for c in self.cohorts)
        plants = sum(c.n for c in self.cohorts)
        # Biomass-weighted, so a cloud of tiny seedlings does not hide the sward.
        weighted_height = sum(
            allometry.height(c.shoot_c, self._pft_by_id[c.pft]) * c.shoot_c * c.n
            for c in self.cohorts
        )
        out = {
            "shoot_c": shoot / area_m2,
            "root_c": root / area_m2,
            "biomass_c": (shoot + root) / area_m2,
            "plants": plants / area_m2,
            "mean_height": weighted_height / shoot if shoot > 0 else 0.0,
            "gpp": self.last_annual_gpp,
            "npp": self.last_annual_npp,
            "harvest_c": self.last_harvest_c,
            "cumulative_harvest_c": self.exported_c,
            "fixed_n": self.last_annual_fixed_n,
            "n_limitation": self._n_limitation,
            "cohorts": len(self.cohorts),
            "shannon_diversity": self._shannon(),
        }
        for p in self.pfts:
            out[f"shoot_c_{p.id}"] = (
                sum(c.shoot_c * c.n for c in self.cohorts if c.pft == p.id) / area_m2
            )
            out[f"plants_{p.id}"] = (
                sum(c.n for c in self.cohorts if c.pft == p.id) / area_m2
            )
        return out

    def _shannon(self) -> float:
        """Shannon diversity over functional groups, by shoot biomass share."""
        import math

        totals = [
            sum(c.shoot_c * c.n for c in self.cohorts if c.pft == p.id) for p in self.pfts
        ]
        total = sum(totals)
        if total <= 0.0:
            return 0.0
        h = 0.0
        for value in totals:
            if value > 0.0:
                share = value / total
                h -= share * math.log(share)
        return h

    def sward_profile(self) -> list[dict]:
        """Per-PFT sward height and cover, for the vertical stand-structure view."""
        profile = []
        for p in self.pfts:
            members = [c for c in self.cohorts if c.pft == p.id and c.n > 0]
            if not members:
                continue
            plants = sum(c.n for c in members)
            profile.append(
                {
                    "pft": p.id,
                    "colour": p.colour,
                    "plants": plants,
                    "shoot_c": sum(c.shoot_c * c.n for c in members),
                    "height": sum(allometry.height(c.shoot_c, p) * c.n for c in members) / plants,
                    "leaf_area": sum(allometry.leaf_area(c.shoot_c, p) * c.n for c in members),
                }
            )
        return profile
