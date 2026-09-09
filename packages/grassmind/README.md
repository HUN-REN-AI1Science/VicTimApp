# grassmind

A port of the **GRASSMIND** individual-based grassland model (UFZ Leipzig),
ported from the published process descriptions — the GRASSMIND papers and the
BioDT grassland prototype digital twin documentation — **not from the upstream
EUPL-1.2 C++ source** ([BioDT/uc-grassland-model](https://github.com/BioDT/uc-grassland-model)).

## What it models

A species-rich managed sward as cohorts of identical herbaceous individuals.
Where FORMIND drives everything from stem diameter, GRASSMIND drives everything
from **shoot carbon**: grasses have no useful stem allometry, so height and leaf
area are saturating functions of accumulated shoot mass. An "individual" here is
a tiller, not a tussock — hence per-plant masses on the order of 10⁻⁴ kgC and
densities of hundreds to thousands per m².

| Module | Process |
|---|---|
| `allometry.py` | Shoot carbon → height, leaf area, ground area (and the inverse, for mowing) |
| `growth.py` | Michaelis–Menten photosynthesis → NPP, plus legume N fixation |
| `mortality.py` | Background turnover and shade mortality |
| `recruitment.py` | Seed establishment |
| `management.py` | Mowing, grazing, fertilisation — and the presets the UI offers |
| `pft.py` | Functional groups and the UI parameter schema |
| `model.py` | `GrasslandModule`, the `ecocore.VegetationModule` implementation |

## Functional groups

Grasses, forbs and **legumes**. The legume group matters more than it looks:
nitrogen is a *shared* resource in `ecocore.soil`, so legume fixation raises
mineral nitrogen for the grasses beside them **and for the trees above them**. It
is the clearest case in this model of a grassland process feeding a forest one.

## Three processes without which the model is wrong

**Remobilisation from root reserves.** After defoliation a grass plant regrows
from carbohydrate stored below ground — it has almost no leaf area left to
photosynthesise with. Without this, a mown sward cannot recover and the model
concludes that any cutting regime destroys the grassland, which is the opposite
of what managed meadows do.

**A large root allocation.** ~62% of net production goes below ground, higher
than a steady state alone would require, because the root system *is* the
regrowth reserve. Under-sizing it reproduces the same failure as omitting
remobilisation.

**Clonal tillering.** A grass individual has a maximum size (`max_shoot_c`);
surplus production above it becomes new individuals rather than a larger one.
Without a size cap, carbon piles into a handful of "plants" carrying kilograms of
carbon each — tree-sized grasses — and sward density collapses.

## Management is emitted, not applied privately

`emit_disturbances` turns today's schedule into `ecocore.Defoliation` events
*before any module steps*. `GrasslandModule` then applies them to the sward from
`ctx.disturbances`, and `formind.ForestModule` applies the same events to its
saplings.

This is the mechanism by which grassland management prevents woody encroachment.
A mower does not merely trim a tree sapling, it cuts it off at the base —
`woody_kill_height_m`. With that set to zero, a mown tile is invaded by trees
within a few decades; with it at 0.6 m, the meadow persists indefinitely.
Fertilisation stays inside this module because it acts on the soil, not on
standing biomass.

### Presets

| Preset | Regime |
|---|---|
| `abandoned` | Nothing. Trees eventually take the site. |
| `extensive_meadow` | One cut at day 190, no fertiliser |
| `intensive_meadow` | Four cuts, two fertiliser applications |
| `pasture` | Season-long grazing, days 120–290 |

## Departures from the published formulation

GRASSMIND does model nitrogen limitation, but as a reduction factor on
assimilation. Four details below are this port's own, recorded so the port stays
auditable against the published descriptions.

| Change | Where | Why |
|---|---|---|
| Nitrogen limitation scales **maintenance respiration**, not only GPP | `growth.py` | Maintenance tracks tissue nitrogen, so a starved sward pays less to hold what it has. Applying the limitation to assimilation alone left upkeep at its unlimited value and killed an unmanaged sward within ~12 years. Largest single effect of any fix here: year-16 sward 0.0007 → 0.0584 kgC m⁻². |
| **Litter nitrogen charged per tissue** (`cn_ratio` for shoot, new `root_cn_ratio` = 50 for root) | `model.py`, `pft.py` | Roots are the larger litter flux and much the poorer in nitrogen; a single shoot ratio overstated the nitrogen leaving. |
| **Growth demand uses an allocation-weighted C:N** (`_mean_growth_cn_ratio`) | `model.py` | `root_fraction` ≈ 0.62, so most new carbon becomes root. Sizing demand on shoot tissue alone overstated it. |
| **Grazing returns nitrogen at its own fraction** (`nitrogen_return_fraction` = 0.85 vs carbon `return_fraction` = 0.4) | `management.py`, `model.py` | A grazer respires most of the carbon it eats but retains only a small part of the nitrogen in meat and milk, so dung and urine are far richer in nitrogen than the herbage was. Returning nitrogen at the carbon fraction exported 60% of it and mined the soil — the slow pool fell to 0.14 kgN m⁻² against 0.25 under abandonment. |

A **plant nitrogen reserve** (`N_RESERVE_DAYS` = 60, `_take_nitrogen`) mirrors
`formind.model`. For a sward it changes *when* a shortfall bites rather than
whether it does, but the timing matters. It is invented by this port and is
load-bearing — see `validation/README.md`.

## Calibration status

> **These figures predate nitrogen limitation and are currently wrong.** They
> were measured before the shared soil column limited growth, and standing crop
> is now roughly half to a third of what this table shows (meadow ~46, pasture
> ~18 gC m⁻²). Two behaviour tests are red. See `validation/README.md`,
> "Nitrogen limitation", before quoting any number here.

Thirty-year runs at a temperate site give:

| Regime | Shoot (gC m⁻²) | Root (gC m⁻²) | LAI | Harvest (gC m⁻² y⁻¹) |
|---|---|---|---|---|
| Abandoned | 160 | 347 | 4.0 | — |
| Extensive meadow | 107 | 232 | 2.3 | 136 |
| Pasture | 46 | 102 | 1.1 | 130 |
| Intensive meadow | 19 | 49 | 0.6 | 111 |

Standing crop, root:shoot ratio and extensive-meadow yield (~310 g DM m⁻² y⁻¹)
are in the observed range for temperate managed grassland.

**Two known gaps.** Intensive multi-cut regimes are under-productive — real
intensive silage yields 600–1000 g DM m⁻² y⁻¹ against our ~250, so the ranking
between intensive and extensive is wrong even though every regime is
individually plausible. And competitive exclusion is too fast: unmanaged and
extensively mown swards converge on grass monoculture (Shannon H′ → 0) because
the three groups lack the niche differentiation that maintains real
species-richness. Frequent disturbance does maintain diversity (H′ ≈ 0.7 under
the intensive regime), which is the right direction.

`maintenance_respiration` is the single most sensitive parameter: living biomass
equilibrates near NPP divided by it, so 0.008 d⁻¹ silently caps a temperate sward
at a third of its observed standing crop.

## Tests

```bash
uv run pytest packages/grassmind/tests -q
```
