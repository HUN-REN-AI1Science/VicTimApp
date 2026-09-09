"""The shared vertical light profile -- the coupling's primary currency.

One profile per tile. Trees and grass deposit leaf area into the SAME layer
stack, so grass necessarily receives only radiation transmitted through the tree
canopy above it. This is what makes forest-grassland competition mechanistic
rather than a cover-fraction blend.

Method (FORMIND Handbook, light climate / canopy geometry section):
  * The canopy is cut into horizontal layers of `LAYER_HEIGHT_M`.
  * Each cohort spreads its leaf area uniformly over the layers its crown spans.
  * Irradiance is attenuated downwards layer by layer with Lambert-Beer,
        I(below) = I(above) * exp(-k_eff * LAI_layer)
    using a leaf-area-weighted mean k for each layer.
  * Radiation absorbed by a layer is split among the cohorts present in it in
    proportion to their k * leaf_area share.

Conservation: sum(absorbed) + floor == incident, exactly, by construction.
`packages/ecocore/tests/test_light.py` asserts this every step -- it is the
automated guard against the double-counting failure mode.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Hashable, Iterable, Sequence

import numpy as np

from .cohort import CanopyElement
from .units import LAYER_HEIGHT_M

__all__ = ["LightProfile", "LightResult", "compute_light"]


@dataclass
class LightResult:
    """Per-cohort light, resolved from one shared profile."""

    incident_par: float
    """PAR arriving at the top of the canopy (umol m-2 s-1)."""

    floor_par: float
    """PAR reaching the ground (umol m-2 s-1). Gates seedling establishment."""

    absorbed_par: dict[Hashable, float] = field(default_factory=dict)
    """PAR absorbed by each cohort, expressed per m2 of GROUND (umol m-2 s-1).

    Multiply by tile area for the cohort's total flux. Summing this over all
    cohorts and adding `floor_par` reproduces `incident_par`.
    """

    mean_incident_par: dict[Hashable, float] = field(default_factory=dict)
    """Leaf-area-weighted mean irradiance ON the leaves of each cohort.

    This, not `absorbed_par`, is what feeds the Michaelis-Menten light-response
    curve in both `formind.growth` and `grassmind.growth`.
    """

    layer_top_par: np.ndarray = field(default_factory=lambda: np.zeros(0))
    """Irradiance entering each layer, index 0 = lowest layer."""

    lai_by_layer: np.ndarray = field(default_factory=lambda: np.zeros(0))
    """Leaf area index of each layer, index 0 = lowest layer."""

    @property
    def total_lai(self) -> float:
        return float(self.lai_by_layer.sum())

    @property
    def absorbed_total(self) -> float:
        return float(sum(self.absorbed_par.values()))


def compute_light(
    elements: Sequence[CanopyElement],
    incident_par: float,
    tile_area_m2: float,
) -> LightResult:
    """Resolve one tile's light climate for one day.

    Fully vectorised: the downward attenuation is a reverse cumulative sum of
    optical depth rather than a Python loop over layers, which matters because
    this runs once per tile per simulated day and a century-scale run is ~36,500
    calls per tile.

    Args:
        elements: every cohort in the tile, trees and grass together. Passing
            them in separate calls would defeat the entire coupling.
        incident_par: PAR above the canopy (umol m-2 s-1).
        tile_area_m2: ground area the leaf areas are spread over.
    """
    if tile_area_m2 <= 0.0:
        raise ValueError("tile_area_m2 must be positive")

    live = [e for e in elements if e.leaf_area_m2 > 0.0]
    if not live:
        return LightResult(
            incident_par=incident_par,
            floor_par=incident_par,
            layer_top_par=np.array([incident_par]),
            lai_by_layer=np.zeros(1),
        )

    canopy_top = max(e.top_m for e in live)
    n_layers = max(1, math.ceil(canopy_top / LAYER_HEIGHT_M))

    base = np.array([e.base_m for e in live])
    top = np.array([e.top_m for e in live])
    area = np.array([e.leaf_area_m2 for e in live])
    k = np.array([e.k for e in live])

    # --- spread each cohort's leaf area over the layers its crown spans ---
    edges_lo = np.arange(n_layers) * LAYER_HEIGHT_M
    edges_hi = edges_lo + LAYER_HEIGHT_M
    overlap = np.clip(
        np.minimum(edges_hi[None, :], top[:, None]) - np.maximum(edges_lo[None, :], base[:, None]),
        0.0,
        None,
    )
    span = (top - base)[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        fraction = np.where(span > 1e-9, overlap / np.maximum(span, 1e-30), 0.0)

    # Degenerate crowns (seedlings, short grass) collapse into one layer.
    degenerate = (top - base) <= 1e-9
    if degenerate.any():
        idx = np.clip((top[degenerate] // LAYER_HEIGHT_M).astype(int), 0, n_layers - 1)
        fraction[degenerate] = 0.0
        fraction[np.flatnonzero(degenerate), idx] = 1.0

    leaf_area = area[:, None] * fraction
    lai = leaf_area.sum(axis=0) / tile_area_m2

    la_by_layer = leaf_area.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        k_eff = np.where(la_by_layer > 0.0, (k[:, None] * leaf_area).sum(axis=0) / la_by_layer, 0.0)

    # --- attenuate top-down via cumulative optical depth ---
    optical_depth = k_eff * lai
    # Depth accumulated ABOVE each layer: reverse exclusive cumulative sum.
    depth_above = np.cumsum(optical_depth[::-1])[::-1] - optical_depth
    layer_top_par = incident_par * np.exp(-depth_above)
    transmittance = np.exp(-optical_depth)
    layer_absorbed = layer_top_par * (1.0 - transmittance)
    floor_par = float(layer_top_par[0] * transmittance[0]) if n_layers else incident_par

    share_weight = k[:, None] * leaf_area
    total_weight = share_weight.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        share = np.where(total_weight > 0.0, share_weight / total_weight, 0.0)
    absorbed = (share * layer_absorbed).sum(axis=1)
    weighted_incident = (leaf_area * layer_top_par).sum(axis=1)

    total_leaf_area = leaf_area.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_incident = np.where(
            total_leaf_area > 0.0, weighted_incident / np.maximum(total_leaf_area, 1e-30),
            incident_par,
        )

    return LightResult(
        incident_par=incident_par,
        floor_par=floor_par,
        absorbed_par={e.key: float(absorbed[i]) for i, e in enumerate(live)},
        mean_incident_par={e.key: float(mean_incident[i]) for i, e in enumerate(live)},
        layer_top_par=layer_top_par,
        lai_by_layer=lai,
    )


class LightProfile:
    """Accumulates canopy elements from every model, then resolves them together.

    Usage per tile per day::

        profile = LightProfile(tile_area_m2)
        profile.add(forest.canopy_elements())
        profile.add(grass.canopy_elements())
        light = profile.resolve(incident_par)

    The two `add` calls before a single `resolve` are the coupling. Resolving
    twice with disjoint element sets would double-count the incident radiation.
    """

    def __init__(self, tile_area_m2: float) -> None:
        self.tile_area_m2 = tile_area_m2
        self._elements: list[CanopyElement] = []

    def add(self, elements: Iterable[CanopyElement]) -> None:
        self._elements.extend(elements)

    def clear(self) -> None:
        self._elements.clear()

    @property
    def elements(self) -> list[CanopyElement]:
        return list(self._elements)

    def resolve(self, incident_par: float) -> LightResult:
        return compute_light(self._elements, incident_par, self.tile_area_m2)
