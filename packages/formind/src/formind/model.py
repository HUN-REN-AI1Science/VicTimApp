"""The forest vegetation module -- FORMIND's process chain behind ecocore's contract.

`ForestModule` is a `ecocore.tile.VegetationModule`. It never imports `grassmind`
and has no idea grass exists; everything the grass does reaches it as less light
at its crowns, less light on the forest floor, and less water in the shared soil
column. That indirection is the design, not an accident of layering.

Departures from the published formulation
-----------------------------------------

Both concern nitrogen, which the FORMIND Handbook does not model -- FORMIND is
light- and space-limited -- so neither has a published equation behind it:

1. **A plant nitrogen reserve** (`N_RESERVE_DAYS`, `_take_nitrogen`). A tree does
   not stop photosynthesising the day its uptake falls short; nitrogen is
   buffered in living tissue and remobilised. Without the reserve the limitation
   was the raw `granted / demand` of a single day, which put the deepest cut on
   the most productive days of the year, because demand peaks when growth peaks.
   This parameter is INVENTED BY THIS PORT and is load-bearing -- see
   `validation/README.md`, "Do not close the gap by tuning `N_RESERVE_DAYS`".

2. **Litter nitrogen charged per tissue.** Leaf litter is charged at
   `leaf_cn_ratio` and root litter at `root_cn_ratio` rather than both at the
   leaf ratio. Root turnover is a large share of the total and much poorer in
   nitrogen, so one ratio for both overstated the nitrogen the stand must
   replace by about a quarter.

The carbon side of the module is unchanged from the Handbook.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ecocore.cohort import CanopyElement, Cohort
from ecocore.soil import LitterInput
from ecocore.tile import StepContext
from ecocore.weather import DayWeather

from . import allometry, mortality, recruitment
from .growth import daily_carbon_balance
from .recruitment import BREAST_HEIGHT_M, SeedlingCohort
from .pft import DEFAULT_TREE_PFTS, TreePFT

__all__ = ["TreeCohort", "ForestModule"]

PLANT_CN_RATIO = 120.0
"""C:N of NEW tree tissue, used to size nitrogen demand from carbon gain.

Woody, so much wider than the C:N of the leaf and fine-root litter the tree sheds
each year -- which is why nitrogen demand has to cover both (see `step_day`).
"""

N_RESERVE_DAYS = 60.0
"""Days of nitrogen demand a stand can carry internally. See `_take_nitrogen`.

NOT a ported parameter -- see the module docstring, "Departures". Load-bearing:
at 90 days an abandoned tile is never invaded at all.
"""

MERGE_LOG_BINS_PER_DECADE = 20
"""Logarithmic diameter classes per decade, for cohort merging.

Logarithmic rather than linear because tree diameter spans four orders of
magnitude between a 0.25 mm seedling and a 1 m veteran; a linear bin fine enough
for seedlings would leave thousands of classes among mature trees, and one coarse
enough for mature trees would merge a 0.3 m seedling with a 6 m sapling.
"""


@dataclass
class TreeCohort(Cohort):
    """A group of identical trees.

    State is the diameter; every other quantity is derived from it through
    `allometry`, which is what makes this a FORMIND-style model rather than a
    generic biomass pool model.
    """

    dbh: float = 0.02
    increment_accumulator: float = 0.0
    last_annual_increment: float = 0.0

    def sync_biomass(self, p: TreePFT) -> None:
        aboveground = allometry.aboveground_biomass_c(self.dbh, p)
        self.leaf_c = aboveground * p.leaf_fraction
        self.stem_c = aboveground - self.leaf_c
        self.root_c = aboveground * p.root_fraction


@dataclass
class ForestModule:
    """FORMIND process chain for one tile."""

    pfts: list[TreePFT] = field(default_factory=lambda: list(DEFAULT_TREE_PFTS))
    cohorts: list[TreeCohort] = field(default_factory=list)
    seedlings: list[SeedlingCohort] = field(default_factory=list)
    """Sub-breast-height regeneration. See `formind.recruitment`."""
    name: str = "forest"

    # Running diagnostics, reset annually.
    annual_gpp: float = 0.0
    annual_npp: float = 0.0
    last_annual_gpp: float = 0.0
    last_annual_npp: float = 0.0
    _last_gpp: float = 0.0
    _last_npp: float = 0.0
    _n_limitation: float = 1.0
    _n_reserve: float = 0.0
    """Plant-held nitrogen buffer (kgN m-2). See `_take_nitrogen`."""
    _absorbed_fraction: float = 0.0

    def __post_init__(self) -> None:
        self._pft_by_id = {p.id: p for p in self.pfts}
        for cohort in self.cohorts:
            cohort.sync_biomass(self._pft_by_id[cohort.pft])

    # ------------------------------------------------------------- setup ----

    @classmethod
    def bare_ground(cls, pfts: list[TreePFT] | None = None) -> "ForestModule":
        return cls(pfts=list(pfts or DEFAULT_TREE_PFTS), cohorts=[])

    def seed_stand(self, pft_id: str, n: int, dbh: float) -> None:
        """Plant an initial cohort. Used for forest-only reference runs."""
        p = self._pft_by_id[pft_id]
        cohort = TreeCohort(pft=pft_id, n=float(n), dbh=dbh)
        cohort.sync_biomass(p)
        self.cohorts.append(cohort)

    def pft(self, pft_id: str) -> TreePFT:
        return self._pft_by_id[pft_id]

    # -------------------------------------------------- ecocore contract ----

    def canopy_elements(self) -> list[CanopyElement]:
        elements = []
        for cohort in self.cohorts:
            p = self._pft_by_id[cohort.pft]
            if cohort.n <= 0.0 or cohort.dbh <= 0.0:
                continue
            elements.append(
                CanopyElement(
                    key=id(cohort),
                    base_m=allometry.crown_base(cohort.dbh, p),
                    top_m=allometry.height(cohort.dbh, p),
                    leaf_area_m2=allometry.leaf_area(cohort.dbh, p) * cohort.n,
                    k=p.k,
                )
            )
        for seedling in self.seedlings:
            if seedling.n <= 0.0 or seedling.height_m <= 0.0:
                continue
            p = self._pft_by_id[seedling.pft]
            elements.append(
                CanopyElement(
                    key=id(seedling),
                    base_m=0.0,
                    top_m=seedling.height_m,
                    leaf_area_m2=p.seedling_leaf_area_scale * seedling.height_m * seedling.n,
                    k=p.k,
                )
            )
        return elements

    def water_demand_mm(self, day: DayWeather, light) -> float:
        """Transpiration demand, scaled by the share of radiation this module absorbed.

        Partitioning potential evapotranspiration by absorbed light means trees
        and grass automatically divide the atmospheric demand in proportion to
        the canopy each of them actually holds -- no cover-fraction fudge.
        """
        if light.incident_par <= 0.0:
            self._absorbed_fraction = 0.0
            return 0.0
        keys = {id(c) for c in self.cohorts}
        absorbed = sum(v for k, v in light.absorbed_par.items() if k in keys)
        self._absorbed_fraction = absorbed / light.incident_par
        return day.potential_evapotranspiration_mm * self._absorbed_fraction

    def step_day(self, ctx: StepContext) -> None:
        self._apply_disturbances(ctx)
        gpp_total = 0.0
        npp_total = 0.0
        litter_c = 0.0
        litter_n = 0.0

        for cohort in self.cohorts:
            if cohort.n <= 0.0:
                continue
            p = self._pft_by_id[cohort.pft]
            incident = ctx.light.mean_incident_par.get(id(cohort), 0.0)

            balance = daily_carbon_balance(
                dbh=cohort.dbh,
                incident_par=incident,
                daylength_h=ctx.day.daylength_h,
                temperature_c=ctx.day.temperature_c,
                water_supply_fraction=ctx.water_supply_fraction,
                nitrogen_limitation=self._n_limitation,
                p=p,
            )

            gpp_total += balance.gpp * cohort.n
            npp_total += balance.npp * cohort.n

            # Shed tissue returns to the shared soil column.
            litter_c += balance.turnover_cost * cohort.n
            # Nitrogen is resorbed before abscission and reused, so litter is
            # poorer in nitrogen than the living tissue it came from.
            # Leaf and root litter are charged at their OWN C:N. Root turnover is
            # a large share of `turnover_cost` and much poorer in nitrogen, so one
            # leaf ratio for both overstated the nitrogen the stand must replace.
            litter_n += (
                (
                    balance.leaf_turnover_c / p.leaf_cn_ratio
                    + balance.root_turnover_c / p.root_cn_ratio
                )
                * cohort.n
                * (1.0 - p.nitrogen_resorption)
            )

            if balance.diameter_increment > 0.0:
                cohort.dbh = min(p.max_dbh, cohort.dbh + balance.diameter_increment)
                cohort.increment_accumulator += balance.diameter_increment
                cohort.sync_biomass(p)
            cohort.age_days += 1

        if litter_c > 0.0:
            ctx.soil.add_litter(
                LitterInput(
                    carbon=litter_c / ctx.tile_area_m2,
                    nitrogen=litter_n / ctx.tile_area_m2,
                    lignin_fraction=0.3,
                )
            )

        # Nitrogen uptake must cover BOTH new tissue and the nitrogen leaving in
        # shed leaves and roots. Sizing demand on new growth alone makes the plant
        # a net nitrogen source -- it returns litter richer than the tissue it
        # took up -- and mineral nitrogen then accumulates without bound.
        # The resulting limitation applies to tomorrow, avoiding a circular
        # dependency inside one day.
        growth_demand = max(0.0, npp_total) / PLANT_CN_RATIO
        demand = (growth_demand + litter_n) / ctx.tile_area_m2
        self._n_limitation = self._take_nitrogen(ctx, demand)

        self._last_gpp = gpp_total / ctx.tile_area_m2
        self._last_npp = npp_total / ctx.tile_area_m2
        self.annual_gpp += self._last_gpp
        self.annual_npp += self._last_npp

    def step_year(self, ctx: StepContext) -> None:
        self._apply_mortality(ctx)
        self._apply_space_limitation(ctx)
        self._offer_seeds(ctx)
        self._grow_seedlings(ctx)
        self._establish(ctx)

        for cohort in self.cohorts:
            cohort.last_annual_increment = cohort.increment_accumulator
            cohort.increment_accumulator = 0.0
        self.cohorts = [c for c in self.cohorts if not c.is_extinct()]
        self._merge_cohorts()
        self.last_annual_gpp = self.annual_gpp
        self.last_annual_npp = self.annual_npp
        self.annual_gpp = 0.0
        self.annual_npp = 0.0

    # ----------------------------------------------------------- internals --

    def _return_to_soil(self, ctx: StepContext, cohort: TreeCohort, dead: float) -> None:
        p = self._pft_by_id[cohort.pft]
        if dead <= 0.0:
            return
        leaf_c = cohort.leaf_c * dead
        wood_c = (cohort.stem_c + cohort.root_c) * dead
        ctx.soil.add_litter(
            LitterInput(
                carbon=leaf_c / ctx.tile_area_m2,
                nitrogen=leaf_c / p.leaf_cn_ratio / ctx.tile_area_m2,
                lignin_fraction=0.25,
            )
        )
        ctx.soil.add_litter(
            LitterInput(
                carbon=wood_c / ctx.tile_area_m2,
                nitrogen=wood_c / p.wood_cn_ratio / ctx.tile_area_m2,
                lignin_fraction=0.35,
            )
        )

    def _apply_disturbances(self, ctx: StepContext) -> None:
        """Destroy saplings caught by mowing or browsing.

        Established trees are unaffected -- a mower does not top a 20 m beech --
        but a sapling below the cut height is removed at the base. This is the
        mechanism by which grassland management, emitted by `grassmind`, actually
        prevents woody encroachment. Without it the model predicts that every
        managed meadow becomes forest.
        """
        for event in ctx.disturbances:
            if event.woody_kill_height_m <= 0.0 or event.woody_kill_fraction <= 0.0:
                continue
            for cohort in self.cohorts:
                if cohort.n <= 0.0:
                    continue
                p = self._pft_by_id[cohort.pft]
                if allometry.height(cohort.dbh, p) >= event.woody_kill_height_m:
                    continue
                dead = cohort.n * min(1.0, event.woody_kill_fraction)
                if dead > 0.0:
                    self._return_to_soil(ctx, cohort, dead)
                    cohort.n -= dead
            for seedling in self.seedlings:
                if seedling.height_m < event.woody_kill_height_m:
                    seedling.n *= 1.0 - min(1.0, event.woody_kill_fraction)
            self.cohorts = [c for c in self.cohorts if c.n > 1e-9]
            self.seedlings = [sd for sd in self.seedlings if sd.n > 1e-6]

    def _apply_mortality(self, ctx: StepContext) -> None:
        for cohort in self.cohorts:
            p = self._pft_by_id[cohort.pft]
            rate = mortality.annual_mortality_rate(cohort.dbh, cohort.increment_accumulator, p)
            dead = cohort.n * rate
            if dead > 0.0:
                self._return_to_soil(ctx, cohort, dead)
                cohort.n -= dead

    def _apply_space_limitation(self, ctx: StepContext) -> None:
        """Thin overfull height layers, letting crowns stack vertically.

        See `mortality.layered_space_limitation` for why this is per layer rather
        than per patch.
        """
        members = []
        by_key = {}
        for cohort in self.cohorts:
            if cohort.n <= 0.0:
                continue
            p = self._pft_by_id[cohort.pft]
            lo, hi = mortality.layer_range(
                allometry.crown_base(cohort.dbh, p), allometry.height(cohort.dbh, p)
            )
            key = id(cohort)
            by_key[key] = cohort
            members.append((key, cohort.n, allometry.crown_area(cohort.dbh, p), lo, hi))

        removals = mortality.layered_space_limitation(members, ctx.tile_area_m2)
        for key, dead in removals.items():
            cohort = by_key[key]
            dead = min(dead, cohort.n)
            if dead <= 0.0:
                continue
            self._return_to_soil(ctx, cohort, dead)
            cohort.n -= dead

    def _offer_seeds(self, ctx: StepContext) -> None:
        for p in self.pfts:
            mature = sum(
                c.n for c in self.cohorts if c.pft == p.id and c.dbh > 0.3 * p.max_dbh
            )
            if mature > 0.0:
                crown = sum(
                    allometry.crown_area(c.dbh, p) * c.n
                    for c in self.cohorts
                    if c.pft == p.id and c.dbh > 0.3 * p.max_dbh
                )
                ctx.seed_rain.offer(
                    p.id, p.seeds_per_m2_year * min(1.0, crown / ctx.tile_area_m2)
                )

    def _establish(self, ctx: StepContext) -> None:
        """Add this year's germinants to the seedling bank.

        Free space is measured in the GROUND layer, not as total crown area:
        seedlings live under the canopy, so a closed overstorey must not by itself
        forbid regeneration -- only the light it casts should, and that already
        arrives through `ctx.light.floor_par`.
        """
        floor_fraction = self._floor_fraction(ctx)
        ground_occupied = 0.0
        for cohort in self.cohorts:
            p = self._pft_by_id[cohort.pft]
            lo, _ = mortality.layer_range(
                allometry.crown_base(cohort.dbh, p), allometry.height(cohort.dbh, p)
            )
            if lo == 0:
                ground_occupied += allometry.crown_area(cohort.dbh, p) * cohort.n
        free = max(0.0, 1.0 - ground_occupied / ctx.tile_area_m2)

        for p in self.pfts:
            n_new = recruitment.establishment_number(
                ctx.seed_rain.available(p.id), floor_fraction, ctx.tile_area_m2, free, p
            )
            if n_new < 1.0:
                continue
            self.seedlings.append(
                SeedlingCohort(pft=p.id, n=n_new, height_m=p.seedling_height)
            )

    def _take_nitrogen(self, ctx: StepContext, demand: float) -> float:
        """Draw `demand` (kgN m-2) from the shared pool; return tomorrow's limitation.

        A tree does not stop photosynthesising the day its uptake falls short.
        Nitrogen is buffered in living tissue and remobilised, so the module holds
        a reserve worth `N_RESERVE_DAYS` of demand: surplus uptake on a slack day
        fills it, and a shortfall is met from it before growth is cut.

        Without the reserve the limitation was the raw `granted / demand` of a
        single day, and because demand peaks exactly when growth peaks, the
        deepest cut landed on the most productive days of the year. NPP is a small
        difference between GPP and respiration, so that timing turned a ~20% mean
        cut in GPP into a several-fold collapse in NPP -- an unmanaged sward died
        within ~12 years and trees invaded a decade early.
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

    def _grow_seedlings(self, ctx: StepContext) -> None:
        """Advance the seedling bank by one year and promote what reached breast height.

        This is the regeneration bottleneck. A seedling needs several years of
        adequate light to cross 1.3 m, and anything that removes it in the
        meantime -- shade from the sward, shade from the canopy, a mower, a
        grazing animal -- prevents a tree from ever existing.
        """
        floor_fraction = self._floor_fraction(ctx)
        survivors: list[SeedlingCohort] = []
        for seedling in self.seedlings:
            p = self._pft_by_id[seedling.pft]
            seedling.n *= 1.0 - recruitment.seedling_mortality_rate(floor_fraction, p)
            if seedling.n < 1.0:
                continue
            seedling.height_m += recruitment.seedling_height_growth(floor_fraction, p)
            seedling.age_years += 1

            if seedling.height_m >= BREAST_HEIGHT_M:
                cohort = TreeCohort(pft=p.id, n=seedling.n, dbh=p.initial_dbh)
                cohort.sync_biomass(p)
                self.cohorts.append(cohort)
            else:
                survivors.append(seedling)
        self.seedlings = survivors
        self._merge_seedlings()

    def _merge_seedlings(self) -> None:
        """Collapse seedling cohorts of the same PFT in the same 5 cm height class."""
        if len(self.seedlings) < 2:
            return
        buckets: dict[tuple[str, int], SeedlingCohort] = {}
        merged: list[SeedlingCohort] = []
        for seedling in self.seedlings:
            key = (seedling.pft, int(seedling.height_m / 0.05))
            existing = buckets.get(key)
            if existing is None:
                buckets[key] = seedling
                merged.append(seedling)
                continue
            total = existing.n + seedling.n
            existing.height_m = (
                existing.height_m * existing.n + seedling.height_m * seedling.n
            ) / total
            existing.age_years = max(existing.age_years, seedling.age_years)
            existing.n = total
        self.seedlings = merged

    def _floor_fraction(self, ctx: StepContext) -> float:
        if ctx.light.incident_par <= 0.0:
            return 1.0
        return ctx.light.floor_par / ctx.light.incident_par

    def _merge_cohorts(self) -> None:
        """Collapse cohorts of the same PFT that have grown into the same size class.

        Without this, recruitment creates a new cohort every year and the cohort
        list grows without bound, which is why every cohort-based forest model
        merges. Bins are `MERGE_DBH_BIN` wide and the merged diameter is the
        individual-weighted mean, so the biomass error introduced by the
        non-linear diameter-biomass allometry stays far below the model's own
        parameter uncertainty.
        """
        if len(self.cohorts) < 2:
            return
        buckets: dict[tuple[str, int], TreeCohort] = {}
        merged: list[TreeCohort] = []
        for cohort in self.cohorts:
            key = (cohort.pft, int(math.log10(max(cohort.dbh, 1e-9)) * MERGE_LOG_BINS_PER_DECADE))
            existing = buckets.get(key)
            if existing is None:
                buckets[key] = cohort
                merged.append(cohort)
                continue
            total = existing.n + cohort.n
            if total <= 0.0:
                continue
            existing.dbh = (existing.dbh * existing.n + cohort.dbh * cohort.n) / total
            existing.increment_accumulator = (
                existing.increment_accumulator * existing.n
                + cohort.increment_accumulator * cohort.n
            ) / total
            existing.age_days = int(
                (existing.age_days * existing.n + cohort.age_days * cohort.n) / total
            )
            existing.n = total
            existing.sync_biomass(self._pft_by_id[existing.pft])
        self.cohorts = merged

    # -------------------------------------------------------- diagnostics ---

    def diagnostics(self, area_m2: float) -> dict:
        """Forest state, all per m2 of ground. See `ecocore.tile.VegetationModule`."""
        total_c = sum(c.total_c for c in self.cohorts) / area_m2
        stems = sum(c.n for c in self.cohorts) / area_m2
        basal = sum(math.pi * 0.25 * c.dbh**2 * c.n for c in self.cohorts) / area_m2
        stem_count = sum(c.n for c in self.cohorts)
        mean_dbh = (
            sum(c.dbh * c.n for c in self.cohorts) / stem_count if stem_count > 0 else 0.0
        )
        out = {
            "biomass_c": total_c,
            "stems": stems,
            "basal_area": basal,
            "mean_dbh": mean_dbh,
            "max_dbh": max((c.dbh for c in self.cohorts), default=0.0),
            "gpp": self.last_annual_gpp,
            "npp": self.last_annual_npp,
            "n_limitation": self._n_limitation,
            "cohorts": len(self.cohorts),
            "seedlings": sum(sd.n for sd in self.seedlings) / area_m2,
            "seedling_cohorts": len(self.seedlings),
        }
        for p in self.pfts:
            out[f"biomass_c_{p.id}"] = (
                sum(c.total_c for c in self.cohorts if c.pft == p.id) / area_m2
            )
            out[f"stems_{p.id}"] = sum(c.n for c in self.cohorts if c.pft == p.id) / area_m2
        return out

    def stand_profile(self) -> list[dict]:
        """Per-cohort geometry for the vertical stand-structure view.

        FORMIND is horizontally position-free within a patch, so the frontend
        places crowns itself; what it needs from the model is height, crown depth
        and crown width, which is exactly what this returns.
        """
        profile = []
        for cohort in self.cohorts:
            p = self._pft_by_id[cohort.pft]
            profile.append(
                {
                    "pft": cohort.pft,
                    "colour": p.colour,
                    "n": cohort.n,
                    "dbh": cohort.dbh,
                    "height": allometry.height(cohort.dbh, p),
                    "crown_base": allometry.crown_base(cohort.dbh, p),
                    "crown_diameter": allometry.crown_diameter(cohort.dbh, p),
                }
            )
        return sorted(profile, key=lambda r: r["height"], reverse=True)

    def dbh_histogram(self, bin_width: float = 0.1, n_bins: int = 12) -> list[dict]:
        """Stem number by diameter class -- the classic FORMIND output chart."""
        bins = [0.0] * n_bins
        for cohort in self.cohorts:
            idx = min(n_bins - 1, int(cohort.dbh / bin_width))
            bins[idx] += cohort.n
        return [
            {"lower": i * bin_width, "upper": (i + 1) * bin_width, "stems": bins[i]}
            for i in range(n_bins)
        ]
