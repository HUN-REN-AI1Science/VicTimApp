"""Cohort state and the geometry contract the light module consumes.

A cohort is a group of identical individuals of one plant functional type (PFT)
sharing one tile. Both `formind` (trees) and `grassmind` (herbaceous plants)
subclass nothing here -- they build `CanopyElement`s from their own state. This
keeps all species biology out of ecocore, as required by the package boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable

__all__ = ["Cohort", "CanopyElement"]


@dataclass
class Cohort:
    """A group of identical individuals.

    Carbon compartments are **per individual** (kgC), following FORMIND's
    individual-based bookkeeping. Multiply by `n` for tile totals.
    """

    pft: str
    n: float
    leaf_c: float = 0.0
    stem_c: float = 0.0
    root_c: float = 0.0
    age_days: int = 0
    # Set by the owning model each step; read by diagnostics and the API.
    extras: dict = field(default_factory=dict)

    @property
    def biomass_c(self) -> float:
        """Total carbon of one individual (kgC)."""
        return self.leaf_c + self.stem_c + self.root_c

    @property
    def total_c(self) -> float:
        """Total carbon of the whole cohort (kgC)."""
        return self.biomass_c * self.n

    def is_extinct(self, min_individuals: float = 1e-9) -> bool:
        return self.n <= min_individuals or self.biomass_c <= 0.0


@dataclass(frozen=True)
class CanopyElement:
    """One cohort's contribution to the shared vertical light profile.

    This is the *entire* interface between a plant model and the light module.
    A model that cannot express itself as canopy elements cannot participate in
    the coupling -- which is deliberate: it forces both models through one
    Lambert-Beer profile instead of each computing its own.
    """

    key: Hashable
    """Identifies the owning cohort so absorbed light can be routed back."""

    base_m: float
    """Height of the bottom of the leaf-bearing volume (m)."""

    top_m: float
    """Height of the top of the leaf-bearing volume (m)."""

    leaf_area_m2: float
    """One-sided leaf area of the WHOLE cohort (m2), i.e. per-individual x n."""

    k: float
    """Lambert-Beer light extinction coefficient (dimensionless)."""

    def __post_init__(self) -> None:
        if self.top_m < self.base_m:
            raise ValueError(f"CanopyElement {self.key}: top_m < base_m")
        if self.leaf_area_m2 < 0.0:
            raise ValueError(f"CanopyElement {self.key}: negative leaf area")
        if not 0.0 < self.k <= 1.0:
            raise ValueError(f"CanopyElement {self.key}: k={self.k} outside (0, 1]")
