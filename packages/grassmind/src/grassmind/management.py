"""Grassland management -- GRASSMIND's distinguishing capability.

Mowing, grazing and fertilisation are the reason a grassland model is needed at
all: an unmanaged temperate grassland becomes forest. These are the headline
controls the browser UI exposes, and the lever a user pulls to watch a tile flip
between grassland and woodland.

Each action reports what it removed or added so the tile's carbon and nitrogen
budget stays auditable: mown biomass is EXPORTED from the site (it leaves as
hay), grazed biomass is partly returned as dung.

Departures from the published formulation
-----------------------------------------

Grazing returns carbon and nitrogen to the sward at DIFFERENT fractions
(`return_fraction` vs `nitrogen_return_fraction`). A single return fraction for
both, which is how the intake is usually written up, implies a grazer excretes
carbon and nitrogen in the proportions it ate them. It does not: it respires most
of the carbon and retains only a small part of the nitrogen in meat and milk, so
dung and urine are far richer in nitrogen than the herbage was. Returning
nitrogen at the carbon fraction exported 60% of it and mined the soil.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["ManagementSchedule", "MowingEvent", "GrazingPeriod", "FertilisationEvent"]


@dataclass(frozen=True)
class MowingEvent:
    """A cut on a given day of year, down to `cut_height_m`."""

    day_of_year: int
    cut_height_m: float = 0.07
    removal_fraction: float = 0.9
    """Share of cut biomass carted off site; the rest stays as litter."""
    woody_kill_height_m: float = 0.6
    """Tree saplings shorter than this are destroyed by the cut.

    This single parameter is what keeps a hay meadow a hay meadow. Set it to zero
    and the tile will be invaded by trees within a few decades even under annual
    mowing, which is not what managed grasslands do.
    """


@dataclass(frozen=True)
class GrazingPeriod:
    """Continuous stocking between two days of year."""

    start_day: int
    end_day: int
    intake_fraction_per_day: float = 0.02
    """Fraction of standing shoot biomass eaten per day."""
    return_fraction: float = 0.4
    """Share of intake CARBON returned to soil as dung; the rest is respired."""
    nitrogen_return_fraction: float = 0.85
    """Share of intake NITROGEN returned to soil as dung and urine.

    Far higher than the carbon share: a grazing animal respires most of the carbon
    it eats but retains only a small part of the nitrogen in meat and milk, so
    75-90% of ingested nitrogen goes straight back onto the sward. Returning
    nitrogen at the carbon fraction instead exported 60% of it, which mined the
    soil -- the slow pool fell to 0.14 kgN m-2 against 0.25 under abandonment --
    and left the pasture permanently nitrogen-limited.
    """
    min_height_m: float = 0.04
    """Animals cannot graze below this height."""
    woody_kill_height_m: float = 0.4
    """Tree saplings shorter than this are browsed out."""
    woody_kill_fraction: float = 0.02
    """Daily probability that a browsable sapling is destroyed.

    Lower than mowing's, because browsing is continuous and selective rather than
    a single clean cut, but applied on every grazing day.
    """


@dataclass(frozen=True)
class FertilisationEvent:
    """Mineral nitrogen application (kgN m-2)."""

    day_of_year: int
    nitrogen_kg_m2: float = 0.005


@dataclass
class ManagementSchedule:
    """The full management regime for a tile."""

    mowing: list[MowingEvent] = field(default_factory=list)
    grazing: list[GrazingPeriod] = field(default_factory=list)
    fertilisation: list[FertilisationEvent] = field(default_factory=list)

    def mowing_today(self, day_of_year: int) -> MowingEvent | None:
        for event in self.mowing:
            if event.day_of_year == day_of_year:
                return event
        return None

    def grazing_today(self, day_of_year: int) -> GrazingPeriod | None:
        for period in self.grazing:
            if period.start_day <= day_of_year <= period.end_day:
                return period
        return None

    def fertilisation_today(self, day_of_year: int) -> float:
        return sum(
            e.nitrogen_kg_m2 for e in self.fertilisation if e.day_of_year == day_of_year
        )

    @property
    def is_empty(self) -> bool:
        return not (self.mowing or self.grazing or self.fertilisation)

    # ------------------------------------------------------------ presets ---

    @classmethod
    def abandoned(cls) -> "ManagementSchedule":
        """No management. The regime under which trees take the site."""
        return cls()

    @classmethod
    def extensive_meadow(cls) -> "ManagementSchedule":
        """One late cut a year, no fertiliser -- species-rich hay meadow."""
        return cls(mowing=[MowingEvent(day_of_year=190)])

    @classmethod
    def intensive_meadow(cls) -> "ManagementSchedule":
        """Four cuts and two fertiliser applications -- productive silage."""
        return cls(
            mowing=[MowingEvent(day_of_year=d) for d in (135, 175, 215, 255)],
            fertilisation=[
                FertilisationEvent(day_of_year=100, nitrogen_kg_m2=0.008),
                FertilisationEvent(day_of_year=180, nitrogen_kg_m2=0.006),
            ],
        )

    @classmethod
    def pasture(cls) -> "ManagementSchedule":
        """Season-long grazing."""
        return cls(grazing=[GrazingPeriod(start_day=120, end_day=290)])
