# formind

A port of the **FORMIND** individual-based forest gap model (UFZ Leipzig), ported
from the published process descriptions — the FORMIND Handbook and the FORMIND
model papers — **not from the upstream C++ source**.

## What it models

Trees as cohorts of identical individuals within a 20 m × 20 m patch. FORMIND is
a *diameter-driven* model: a tree's state is its stem diameter at breast height,
and height, crown geometry, leaf area and biomass are all derived from it by
power-law allometries fitted per plant functional type. Growth means converting a
carbon increment into a diameter increment.

| Module | Process | Provenance |
|---|---|---|
| `allometry.py` | DBH → height, crown, leaf area, biomass; and the inverse | Handbook, "Tree geometry" |
| `growth.py` | Crown-integrated Michaelis–Menten photosynthesis → NPP → ΔDBH | Handbook, "Tree growth" |
| `mortality.py` | Background, size-, growth-dependent; layer-wise space limitation | Handbook, "Mortality" |
| `recruitment.py` | Establishment and the sub-breast-height seedling bank | Handbook, "Recruitment" |
| `pft.py` | Plant functional types and the UI parameter schema | Handbook, "Plant functional types" |
| `model.py` | `ForestModule`, the `ecocore.VegetationModule` implementation | — |

## State variables

| Quantity | Unit | Held as |
|---|---|---|
| Stem diameter | m | `TreeCohort.dbh` — the state; everything else derives |
| Leaf / stem / root carbon | kgC **per individual** | synced from allometry each step |
| Individuals | count per tile | `TreeCohort.n` |
| Seedling height | m | `SeedlingCohort.height_m` |

`diagnostics(area_m2)` returns everything **per m² of ground**.

## Three decisions that carry the model

**Photosynthesis is integrated analytically over the crown.** The closed form
`(pmax/k) · ln[(αkI + pmax(1−m)) / (αkI·e^(−k·LAI) + pmax(1−m))]` is what lets a
gap model carry thousands of individuals cheaply. Incident irradiance arrives
from `ecocore.light`, already attenuated by every other tree *and* by the grass
sward below.

**Space limitation is evaluated per height layer, not per patch.** A global
crown-area limit forbids a tall tree and a short tree from occupying the same
ground, which pins stand LAI near a single crown's LAI (~1.8) and leaves an
implausibly bright forest floor (~26% of incident light). Layer-wise limiting
produces realistic multi-layered stands: LAI ~4.2, floor light ~4%.

**Seedlings live in their own bank, tracked by height.** DBH is undefined below
breast height, so a seedling cannot be represented as a very thin tree — the
diameter allometry, fitted on mature stems, then predicts that a 0.25 mm recruit
is 0.3 m tall and reaches 4 m within one season. That single artefact makes tree
invasion of grassland unstoppable and mowing irrelevant. Seedlings are therefore
promoted into the tree cohort list only on reaching 1.3 m, and the years they
spend climbing are the real regeneration bottleneck — where the sward shades
them, and where a mower or a grazing animal removes them.

## How grass suppresses tree regeneration

There is no code for it, and there must not be. Grass leaf area sits in the same
Lambert–Beer profile as tree leaf area, so `ctx.light.floor_par` is already
lowered by the sward. Establishment and seedling survival read that floor light.
An explicit "grass suppresses seedlings" channel would double-count the effect.

Mowing is different: it is a *disturbance*, not a resource, so it arrives as an
`ecocore.Defoliation` event that this module responds to by destroying saplings
below the cut height.

## Cohort merging

Recruitment creates cohorts every year, so they must be merged or the list grows
without bound. Classes are **logarithmic** in diameter (20 per decade) because
tree diameter spans four orders of magnitude between a seedling and a veteran; a
linear bin fine enough for seedlings leaves thousands of classes among mature
trees. Merged diameter is the individual-weighted mean, so the biomass error from
the non-linear allometry stays far below parameter uncertainty.

## Departures from the published formulation

The FORMIND Handbook models no nitrogen — FORMIND is light- and space-limited —
so everything below is this port's own, introduced when the shared soil column
was coupled to growth. None of it changes the carbon arithmetic when nitrogen
limitation is 1.0, so an uncoupled tree still behaves exactly as the Handbook
describes.

| Change | Where | Why |
|---|---|---|
| Nitrogen limitation scales **maintenance respiration**, not only GPP | `growth.py` | Maintenance is largely protein turnover and ion gradients, so it tracks tissue nitrogen: a starved stand builds thinner tissue and pays less to hold it. Limiting income while leaving upkeep fixed makes NPP — a small difference between two large terms — collapse several-fold for a ~20% cut in GPP. |
| **Leaf and root turnover reported separately** (`CarbonBalance.leaf_turnover_c` / `root_turnover_c`) | `growth.py` | The Handbook needs only the total because it tracks no nitrogen. Litter nitrogen must be charged at each tissue's own C:N. |
| **Litter nitrogen charged per tissue** (`leaf_cn_ratio` / new `root_cn_ratio` = 70) | `model.py`, `pft.py` | Root turnover is a large share of the total and much poorer in nitrogen. One leaf ratio for both overstated the nitrogen the stand must replace by about a quarter. |
| **A plant nitrogen reserve** (`N_RESERVE_DAYS` = 60, `_take_nitrogen`) | `model.py` | A tree does not stop photosynthesising the day uptake falls short; nitrogen is buffered in tissue and remobilised. The raw single-day `granted / demand` put the deepest cut on the most productive days, because demand peaks when growth peaks. |

`N_RESERVE_DAYS` is **invented by this port** — it has no literature value to
appeal to — and it is load-bearing: at 90 days an abandoned tile is never invaded
at all. See `validation/README.md`, "Do not close the gap by tuning
`N_RESERVE_DAYS`".

## Calibration status

> **The stand figures below predate nitrogen limitation.** The 90-year stem
> count in a coupled run is now ~5 ha⁻¹ — not credible, and the clearest sign the
> nitrogen cycle is still mis-scaled. See `validation/README.md`.

Parameter values are literature-typical for temperate European forest, **not a
fitted set**. A 90-year run from bare ground gives LAI ~4.2, floor light ~4%,
soil carbon plateauing near 17 kgC m⁻², and clear pioneer → late-successional
replacement. Basal area (~12 m² ha⁻¹ at 90 years) sits at the low end of the
observed range for mature temperate stands. `cd0` (crown diameter allometry) is
the most sensitive parameter for stand density and floor light.

## Tests

```bash
uv run pytest packages/formind/tests -q          # includes multi-decade runs
uv run pytest packages/formind/tests -m "not slow" -q
```

Behaviour tests assert qualitative patterns — succession happens, stands
self-thin, seedlings must climb — rather than numbers, so recalibration does not
require rewriting them.
