"""Grassland plant functional types.

GRASSMIND represents species-rich swards through functional groups rather than
species lists. The three below are its standard European managed-grassland
grouping -- grasses, forbs and nitrogen-fixing legumes.

The legume group matters more than it looks: because nitrogen is a *shared*
resource in `ecocore.soil`, legume fixation raises mineral nitrogen for the
grasses beside them AND for the trees above them. It is the clearest example in
this model of a grassland process feeding a forest one.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

__all__ = ["GrassPFT", "DEFAULT_GRASS_PFTS", "grass_pft_schema"]


@dataclass
class GrassPFT:
    """One herbaceous functional group."""

    id: str
    label: str

    # --- geometry ---
    max_height: float = 0.8
    """Asymptotic sward height (m)."""
    height_scale: float = 8000.0
    """Rate at which height approaches max_height with shoot carbon (kgC-1).

    Calibrated so a plant carrying ~1e-4 kgC -- a typical tiller in a closed
    sward -- stands at roughly half its maximum height. An individual here is a
    tiller, not a tussock, which is why the mass scale is so small.
    """
    specific_leaf_area: float = 22.0
    """Leaf area per unit leaf carbon (m2 kgC-1)."""
    leaf_fraction_of_shoot: float = 0.75
    plant_lai: float = 1.6
    """Leaf area index within one plant's own footprint."""

    # --- photosynthesis ---
    pmax: float = 16.0
    """Light-saturated rate (umol CO2 m-2 leaf s-1). Herbs out-assimilate trees
    per unit leaf area, which is why grassland can hold a site against tree
    seedlings while light still reaches the ground."""
    alpha: float = 0.05
    k: float = 0.6
    leaf_transmittance: float = 0.1

    # --- allocation, respiration, turnover ---
    root_fraction: float = 0.62
    """Share of net production allocated below ground.

    Far higher than in trees, and higher than it looks necessary for a steady
    state: the root system is the sward's carbohydrate reserve, and it is what
    regrowth after mowing or grazing is actually paid for with. Under-sizing it
    makes the model predict that any repeated cutting regime destroys the
    grassland, which is the opposite of what managed meadows do.
    """
    maintenance_respiration: float = 0.003
    """Fraction of living carbon respired per day.

    This parameter sets the ceiling on standing biomass more tightly than any
    other: living biomass equilibrates near NPP divided by this rate, so a value
    of 0.008 d-1 (2.9 y-1) silently caps a temperate sward at a third of its
    observed standing crop.
    """
    growth_respiration: float = 0.28
    remobilisation_rate: float = 0.12
    """Daily share of the shoot deficit refilled from root reserves.

    After defoliation a grass plant regrows from carbohydrate stored below
    ground, not from current photosynthesis -- it has almost no leaf area left to
    photosynthesise with. Without this process a mown sward cannot recover, and
    the model wrongly predicts that any cutting regime destroys the grassland.
    """
    shoot_turnover_per_year: float = 1.5
    root_turnover_per_year: float = 0.5
    nitrogen_resorption: float = 0.55
    """Share of nitrogen withdrawn from senescing tissue before it is shed.

    Plants recover roughly half to two-thirds of leaf nitrogen before abscission
    and reuse it. Omitting resorption forces uptake to replace the full nitrogen
    content of everything shed each year, which makes the model far more
    nitrogen-limited than any real temperate site.
    """
    lignin_fraction: float = 0.12
    cn_ratio: float = 25.0
    """C:N of SHOOT tissue."""
    root_cn_ratio: float = 50.0
    """C:N of root tissue.

    Roots are structurally cheaper in nitrogen than leaves, and `root_fraction`
    sends most of NPP to them. Charging root growth and root litter at the shoot
    ratio overstated the sward's nitrogen demand by about a quarter -- enough, on
    its own, to keep the sward permanently nitrogen-limited.
    """

    # --- nitrogen ---
    nitrogen_fixing: bool = False
    fixation_rate: float = 0.0
    """kgN fixed per kgC of net production. Non-zero for legumes only."""

    # --- demography ---
    background_mortality: float = 0.35
    """Annual baseline mortality. Herbaceous turnover is fast."""
    shade_mortality_light_fraction: float = 0.06
    """Light fraction at a plant's own leaves below which shading kills it."""
    shade_mortality_max: float = 0.9
    establishment_light_fraction: float = 0.08
    seeds_per_m2_year: float = 900.0
    initial_shoot_c: float = 2.0e-5
    """Carbon of one newly established seedling (kgC)."""
    max_shoot_c: float = 6.0e-4
    """Maximum shoot carbon of one individual (kgC).

    A grass plant cannot grow without bound the way a tree can: past a certain
    size it tillers instead. Surplus production above this cap is diverted to
    clonal offspring (see `GrasslandModule._clonal_pool`), which is how a sward
    converts productivity into density rather than into a few giant individuals.
    """
    max_density_per_m2: float = 6000.0
    """Self-limiting tiller density (m-2). Real closed swards carry thousands."""

    colour: str = "#c9c04a"

    def __post_init__(self) -> None:
        if self.max_height <= 0.0:
            raise ValueError(f"{self.id}: max_height must be positive")
        if self.nitrogen_fixing and self.fixation_rate <= 0.0:
            raise ValueError(f"{self.id}: nitrogen_fixing PFT needs a fixation_rate")


DEFAULT_GRASS_PFTS: list[GrassPFT] = [
    GrassPFT(
        id="grass",
        label="Grasses",
        max_height=0.9,
        pmax=18.0,
        specific_leaf_area=24.0,
        root_fraction=0.68,
        max_shoot_c=6.0e-4,
        seeds_per_m2_year=1200.0,
        colour="#9bbf3c",
    ),
    GrassPFT(
        id="forb",
        label="Forbs",
        max_height=0.6,
        pmax=15.0,
        specific_leaf_area=20.0,
        root_fraction=0.60,
        max_shoot_c=4.0e-4,
        shade_mortality_light_fraction=0.08,
        seeds_per_m2_year=700.0,
        colour="#d98cb3",
    ),
    GrassPFT(
        id="legume",
        label="Legumes (N-fixing)",
        max_height=0.5,
        pmax=14.0,
        specific_leaf_area=19.0,
        root_fraction=0.55,
        max_shoot_c=3.0e-4,
        cn_ratio=16.0,
        nitrogen_fixing=True,
        fixation_rate=0.022,
        seeds_per_m2_year=500.0,
        colour="#e8a33d",
    ),
]


def grass_pft_schema() -> list[dict]:
    """Adjustable-parameter description for the UI's generic form builder."""
    groups = {
        "max_height": "geometry", "height_scale": "geometry",
        "specific_leaf_area": "geometry", "leaf_fraction_of_shoot": "geometry",
        "plant_lai": "geometry",
        "pmax": "photosynthesis", "alpha": "photosynthesis", "k": "photosynthesis",
        "leaf_transmittance": "photosynthesis",
        "root_fraction": "turnover", "maintenance_respiration": "turnover",
        "remobilisation_rate": "turnover",
        "growth_respiration": "turnover", "shoot_turnover_per_year": "turnover",
        "root_turnover_per_year": "turnover", "lignin_fraction": "turnover",
        "cn_ratio": "turnover", "root_cn_ratio": "turnover",
        "nitrogen_resorption": "turnover",
        "nitrogen_fixing": "nitrogen", "fixation_rate": "nitrogen",
        "background_mortality": "demography",
        "shade_mortality_light_fraction": "demography",
        "shade_mortality_max": "demography",
        "establishment_light_fraction": "demography",
        "seeds_per_m2_year": "demography", "initial_shoot_c": "demography",
        "max_density_per_m2": "demography", "max_shoot_c": "demography",
    }
    units = {
        "cn_ratio": "kgC kgN-1", "root_cn_ratio": "kgC kgN-1",
        "max_height": "m", "specific_leaf_area": "m2 kgC-1",
        "pmax": "umol CO2 m-2 s-1", "maintenance_respiration": "d-1",
        "shoot_turnover_per_year": "y-1", "root_turnover_per_year": "y-1",
        "remobilisation_rate": "d-1",
        "fixation_rate": "kgN kgC-1", "background_mortality": "y-1",
        "seeds_per_m2_year": "m-2 y-1", "initial_shoot_c": "kgC",
        "max_density_per_m2": "m-2",
    }
    default = GrassPFT(id="_", label="_")
    schema = []
    for f in fields(GrassPFT):
        if f.name in ("id", "label", "colour"):
            continue
        value = getattr(default, f.name)
        schema.append(
            {
                "name": f.name,
                "group": groups.get(f.name, "other"),
                "unit": units.get(f.name, "-"),
                "default": value,
                "type": "boolean" if isinstance(value, bool) else "number",
            }
        )
    return schema
