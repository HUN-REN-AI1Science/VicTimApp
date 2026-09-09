"""Tree plant functional types.

FORMIND aggregates species into PFTs by maximum diameter and light demand
(FORMIND Handbook, "Plant functional types"), because parameterising hundreds of
species individually is neither tractable nor better constrained. The three types
below span the classic successional gradient of temperate European forest and are
the defaults the API exposes to the UI.

Parameter values are literature-typical for temperate broadleaf/conifer forest.
They are starting points for calibration, not a validated parameter set: see
`validation/` and this package's README.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["TreePFT", "DEFAULT_TREE_PFTS", "tree_pft_schema"]


@dataclass
class TreePFT:
    """One tree functional type."""

    id: str
    label: str

    # --- geometry ---
    h0: float = 42.0
    """Height allometry scale: H = h0 * D^h1 (m, D in m)."""
    h1: float = 0.58
    cd0: float = 12.0
    """Crown diameter allometry scale: CD = cd0 * D^cd1 (m, D in m).

    Calibrated so a 0.2 m DBH tree carries a ~5 m crown and a 0.6 m DBH tree a
    ~9 m crown, which reproduces temperate stand densities of 300-500 stems ha-1
    and basal areas of 25-40 m2 ha-1. Wider crowns cap achievable stand LAI near
    a single crown's LAI and leave an implausibly bright forest floor.
    """
    cd1: float = 0.6
    crown_length_fraction: float = 0.4
    """Crown depth as a fraction of tree height."""
    crown_lai: float = 2.6
    """Leaf area index within the crown volume (m2 m-2)."""

    # --- stem and wood ---
    wood_density: float = 600.0
    """Oven-dry wood density (kg m-3)."""
    form_factor: float = 0.65
    """Stem form factor, correcting the cylinder volume."""
    stem_fraction: float = 0.7
    """Fraction of aboveground biomass held in the stem."""
    root_fraction: float = 0.25
    """Belowground biomass as a fraction of aboveground."""
    leaf_fraction: float = 0.03
    """Leaf biomass as a fraction of aboveground, for litter accounting."""

    # --- photosynthesis ---
    pmax: float = 9.0
    """Light-saturated photosynthesis rate (umol CO2 m-2 leaf s-1)."""
    alpha: float = 0.045
    """Quantum efficiency (umol CO2 per umol photon)."""
    k: float = 0.7
    """Lambert-Beer extinction coefficient."""
    leaf_transmittance: float = 0.1

    # --- respiration and turnover ---
    maintenance_respiration: float = 0.00035
    """Fraction of LIVING carbon respired per day at reference temperature.

    Applied to leaves, roots and sapwood only -- see `sapwood_fraction`.
    """
    sapwood_fraction: float = 0.15
    """Share of stem carbon that is living sapwood.

    Heartwood is dead and does not respire. Charging maintenance respiration
    against total stem mass makes a mature closed stand run a permanent carbon
    deficit, because stem biomass grows without bound while leaf area does not.
    """
    growth_respiration: float = 0.25
    """Fraction of assimilate spent constructing new tissue."""
    leaf_turnover_per_year: float = 0.5
    root_turnover_per_year: float = 0.12
    """Turnover of the WHOLE root system (y-1), coarse roots included.

    Fine roots turn over several times faster, but they are a minority of root
    mass; applying a fine-root rate to total root biomass overstates the flux by
    roughly a factor of three and pushes a closed stand into carbon deficit.
    """
    nitrogen_resorption: float = 0.55
    """Share of nitrogen withdrawn from senescing tissue before it is shed.

    Plants recover roughly half to two-thirds of leaf nitrogen before abscission
    and reuse it. Omitting resorption forces uptake to replace the full nitrogen
    content of everything shed each year, which makes the model far more
    nitrogen-limited than any real temperate site.
    """
    lignin_fraction: float = 0.3
    leaf_cn_ratio: float = 35.0
    wood_cn_ratio: float = 250.0
    root_cn_ratio: float = 70.0
    """C:N of fine and coarse root tissue.

    Root turnover is a large share of `turnover_cost`, and charging it at the
    leaf ratio overstated litter nitrogen -- and so the nitrogen the stand must
    take up to replace it.
    """

    # --- demography ---
    max_dbh: float = 1.0
    """Maximum attainable diameter (m). Growth stops here."""
    background_mortality: float = 0.015
    """Baseline probability of death per year."""
    dbh_mortality_scale: float = 0.06
    """Small trees die faster; this is the diameter scale of that effect (m)."""
    growth_mortality_threshold: float = 0.0008
    """Annual diameter increment (m) below which stress mortality begins."""
    growth_mortality_max: float = 0.25
    """Maximum additional annual mortality from growth suppression."""
    establishment_light_fraction: float = 0.03
    """Minimum floor light, as a fraction of incident, for a seedling to establish."""
    seeds_per_m2_year: float = 0.6
    """Seed production offered to the dispersal kernel, per m2 of crown cover."""
    initial_dbh: float = 2.5e-3
    """Stem diameter at which a seedling is promoted to a tree (m).

    Chosen so `allometry.height(initial_dbh)` lands at roughly breast height
    (1.3 m), because that is where the diameter allometry starts being defined.
    Everything smaller lives in the seedling bank instead -- see
    `recruitment.SeedlingCohort`.
    """
    seedling_height: float = 0.05
    """Height of a newly germinated seedling (m)."""
    seedling_growth_max: float = 0.18
    """Maximum annual height growth of a seedling in full light (m y-1)."""
    seedling_light_half_saturation: float = 0.25
    """Light fraction at which seedling height growth is half its maximum."""
    seedling_mortality: float = 0.16
    """Baseline annual seedling mortality, even in good light.

    Compounds over the many years a seedling needs to reach breast height, so it
    is the most sensitive regeneration parameter in the model: 0.35 y-1 makes
    abandoned grassland permanent, 0.05 y-1 makes mown meadow impossible.
    """
    seedling_leaf_area_scale: float = 0.06
    """Leaf area of a seedling per metre of height (m2 m-1)."""

    colour: str = "#3f7d4e"
    """Map/chart colour, mirroring FORMIND's PFT-coloured stand diagrams."""

    def __post_init__(self) -> None:
        if not 0.0 < self.crown_length_fraction <= 1.0:
            raise ValueError(f"{self.id}: crown_length_fraction must be in (0, 1]")
        if self.max_dbh <= self.initial_dbh:
            raise ValueError(f"{self.id}: max_dbh must exceed initial_dbh")


DEFAULT_TREE_PFTS: list[TreePFT] = [
    TreePFT(
        id="pioneer",
        label="Early-successional pioneer",
        h0=36.0,
        h1=0.55,
        crown_lai=2.0,
        wood_density=420.0,
        pmax=12.0,
        alpha=0.05,
        max_dbh=0.6,
        background_mortality=0.035,
        establishment_light_fraction=0.12,
        seeds_per_m2_year=2.5,
        seedling_growth_max=0.30,
        seedling_light_half_saturation=0.35,
        seedling_mortality=0.20,
        leaf_turnover_per_year=1.0,
        colour="#8fbf5a",
    ),
    TreePFT(
        id="mid",
        label="Mid-successional",
        h0=42.0,
        h1=0.58,
        crown_lai=2.6,
        wood_density=600.0,
        pmax=9.0,
        max_dbh=0.9,
        background_mortality=0.018,
        establishment_light_fraction=0.05,
        seeds_per_m2_year=1.0,
        seedling_growth_max=0.18,
        seedling_light_half_saturation=0.22,
        seedling_mortality=0.16,
        colour="#3f7d4e",
    ),
    TreePFT(
        id="late",
        label="Late-successional shade tolerant",
        h0=45.0,
        h1=0.60,
        crown_lai=3.4,
        wood_density=700.0,
        pmax=7.0,
        alpha=0.055,
        k=0.75,
        max_dbh=1.2,
        background_mortality=0.010,
        establishment_light_fraction=0.02,
        seeds_per_m2_year=0.5,
        seedling_growth_max=0.10,
        seedling_light_half_saturation=0.10,
        seedling_mortality=0.12,
        leaf_turnover_per_year=0.25,
        colour="#1f4f36",
    ),
]


def tree_pft_schema() -> list[dict]:
    """Describe every adjustable parameter for the UI's generic form builder.

    The backend serves this from `GET /api/parameters/formind`; the frontend
    renders it without knowing any parameter names, so adding a parameter here is
    the only edit needed to expose it in the browser.
    """
    from dataclasses import fields

    groups = {
        "h0": "geometry", "h1": "geometry", "cd0": "geometry", "cd1": "geometry",
        "crown_length_fraction": "geometry", "crown_lai": "geometry",
        "wood_density": "stem", "form_factor": "stem", "stem_fraction": "stem",
        "root_fraction": "stem", "leaf_fraction": "stem",
        "pmax": "photosynthesis", "alpha": "photosynthesis", "k": "photosynthesis",
        "leaf_transmittance": "photosynthesis",
        "maintenance_respiration": "turnover", "growth_respiration": "turnover",
        "sapwood_fraction": "turnover",
        "leaf_turnover_per_year": "turnover", "root_turnover_per_year": "turnover",
        "lignin_fraction": "turnover", "leaf_cn_ratio": "turnover",
        "nitrogen_resorption": "turnover",
        "wood_cn_ratio": "turnover", "root_cn_ratio": "turnover",
        "max_dbh": "demography", "background_mortality": "demography",
        "dbh_mortality_scale": "demography",
        "growth_mortality_threshold": "demography",
        "growth_mortality_max": "demography",
        "establishment_light_fraction": "demography",
        "seeds_per_m2_year": "demography", "initial_dbh": "demography",
        "seedling_height": "regeneration", "seedling_growth_max": "regeneration",
        "seedling_light_half_saturation": "regeneration",
        "seedling_mortality": "regeneration",
        "seedling_leaf_area_scale": "regeneration",
    }
    units = {
        "leaf_cn_ratio": "kgC kgN-1", "wood_cn_ratio": "kgC kgN-1",
        "root_cn_ratio": "kgC kgN-1",
        "h0": "m", "cd0": "m", "crown_lai": "m2 m-2", "wood_density": "kg m-3",
        "pmax": "umol CO2 m-2 s-1", "alpha": "umol CO2 umol-1 photon",
        "maintenance_respiration": "d-1", "leaf_turnover_per_year": "y-1",
        "root_turnover_per_year": "y-1", "max_dbh": "m", "initial_dbh": "m",
        "background_mortality": "y-1", "dbh_mortality_scale": "m",
        "growth_mortality_threshold": "m y-1", "growth_mortality_max": "y-1",
        "seeds_per_m2_year": "m-2 y-1", "seedling_height": "m",
        "seedling_growth_max": "m y-1", "seedling_mortality": "y-1",
        "seedling_leaf_area_scale": "m2 m-1",
    }
    schema = []
    default = TreePFT(id="_", label="_")
    for f in fields(TreePFT):
        if f.name in ("id", "label", "colour"):
            continue
        schema.append(
            {
                "name": f.name,
                "group": groups.get(f.name, "other"),
                "unit": units.get(f.name, "-"),
                "default": getattr(default, f.name),
                "type": "number",
            }
        )
    return schema
