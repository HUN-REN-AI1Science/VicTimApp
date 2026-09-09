"""Canonical units for the whole simulation.

Every module in every package MUST use these. Unit drift between the forest and
grassland modules is the single most likely source of a silent scientific bug,
because the two reference models were written with different conventions
(FORMIND steps annually, GRASSMIND daily -- see ecocore/CLAUDE.md).
"""

# Time
DAYS_PER_YEAR = 365
SECONDS_PER_HOUR = 3600.0

# Geometry
LAYER_HEIGHT_M = 0.5
"""Vertical light-profile layer thickness (m).

FORMIND discretises the canopy into horizontal layers of this thickness; the
grass sward of GRASSMIND occupies the lowest one to four of the same layers.
Using one shared discretisation is what makes the coupling physical rather than
a blend of two independent canopies.
"""

DEFAULT_TILE_SIZE_M = 20.0
"""FORMIND's canonical patch edge length (m). A tile is 20 m x 20 m = 400 m^2."""

# Carbon
KG_C_PER_KG_ODM = 0.44
"""Carbon fraction of oven-dry plant matter. FORMIND default."""

# Radiation
PAR_FRACTION_OF_SHORTWAVE = 0.5
"""Fraction of incoming shortwave radiation that is photosynthetically active."""

UMOL_PHOTONS_PER_J_PAR = 4.6
"""Conversion from J of PAR energy to umol of PAR photons."""

# Quantities and their units, for documentation and API schema generation.
UNITS = {
    "par": "umol(photon) m-2 s-1",
    "radiation": "MJ m-2 d-1",
    "temperature": "degC",
    "precipitation": "mm d-1",
    "biomass_carbon": "kgC m-2",
    "cohort_carbon": "kgC per individual",
    "nitrogen": "kgN m-2",
    "water": "mm",
    "lai": "m2 m-2",
    "dbh": "m",
    "height": "m",
    "leaf_area": "m2",
    "gpp": "kgC m-2 d-1",
    "npp": "kgC m-2 d-1",
}
