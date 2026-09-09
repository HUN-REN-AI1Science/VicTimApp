# ecocore

The coupling substrate shared by `formind` and `grassmind`. **Contains no species
biology.** Its entire job is to guarantee that every tile has exactly one
vertical light profile and exactly one soil column, so the two models compete for
real resources instead of each simulating its own site.

## Modules

| Module | Owns |
|---|---|
| `units.py` | Canonical units and the layer/tile geometry constants |
| `cohort.py` | `Cohort` state and `CanopyElement`, the light module's only input |
| `light.py` | The shared vertical profile — Lambert–Beer, vectorised |
| `soil.py` | CENTURY 4.0 pools plus a water bucket |
| `weather.py` | Daily drivers, with a synthetic generator for offline runs |
| `disturbance.py` | `Defoliation`, broadcast to every module in a tile |
| `tile.py` | `Tile.step_day` — the fixed order of operations that *is* the coupling |
| `dispersal.py` | Seed exchange between tiles, once a year |
| `shading.py` | The sky a tile's neighbours take, once a day |
| `grid.py` | The 2D region and the driving loop |

## The daily order of operations

`Tile.step_day` fixes this, and the order is the scientific argument:

0. every module **emits** disturbances (before anyone grows, so module order cannot matter)
1. rain enters the shared soil column, leaching mineral nitrogen with drainage
2. **every** module's canopy is resolved in **one** light profile
3. every module states its water demand
4. the shared column grants water, pro rata if it cannot meet total demand
5. every module grows on the light and water it actually received
6. litter and nitrogen uptake pass through the shared column
7. the column decomposes; at year end, annual bookkeeping runs

Steps 2 and 4 are why this package exists.

## Light

One profile per tile, 0.5 m layers. Each cohort spreads its leaf area over the
layers its crown spans; irradiance attenuates downward as
`I(below) = I(above) · exp(−k_eff · LAI_layer)` with a leaf-area-weighted mean
`k`; radiation absorbed by a layer is split among the cohorts in it by their
`k · leaf_area` share.

**Conservation is exact by construction**: `sum(absorbed) + floor == incident`.
Implemented as a reverse cumulative sum of optical depth rather than a Python
loop — this runs once per tile per simulated day, ~36,500 times per century.

Models read `mean_incident_par` (leaf-area-weighted irradiance *on* a cohort's
leaves) for their light-response curves, not `absorbed_par`.

## Soil

CENTURY 4.0 structure: structural / metabolic litter and active / slow / passive
SOM, each with a maximum decay rate modified by temperature and moisture, plus
mineral nitrogen and a water bucket.

Carbon and nitrogen are conserved to machine precision. `carbon_balance_error`
and `nitrogen_balance_error` close the audit; the nitrogen budget accounts
uptake, fertilisation, biological fixation and leaching separately.

Nitrogen leaves by two routes: plant uptake, and leaching with drainage. Leaching
matters — without it, mineralisation raises mineral nitrogen without bound and a
century-long run ends with thousands of kg N per hectare.

## Lateral shading

The second between-tile flux, and the daily one. A tile standing next to a 30 m
canopy does not receive open-sky irradiance however empty its own profile is, so
`shading.py` gives each tile a **sky view factor** — the share of the hemisphere
its neighbours leave it — and `Tile.step_day` scales incident PAR by it before
the one shared profile is resolved.

Horizon-angle form (Steyn 1980; Oke, *Boundary Layer Climates*, 2nd ed., ch. 8),
over eight azimuth sectors:

```
theta_i = max over tiles along sector i of atan(h_neighbour / d)
SVF     = 1 - (1/N) * sum_i sin²(theta_i)
```

An unobstructed tile has SVF = 1; a 20 m clearing walled in by 30 m forest has
SVF ≈ 0.39. Each tile publishes one scalar, `Tile.canopy_top_m`, and reads its
neighbours’ — no tile ever sees another’s cohorts, and there is still exactly one
light profile and one soil column per tile.

It is a first-order treatment, and the docstring says so: the sun’s position is
not modelled, so all radiation is treated as diffuse; distances are
centre-to-centre, which understates an immediate neighbour; and tiles off the
grid edge count as open sky, the same honest treatment of a finite region that
dispersal gives seeds that leave it. Heights are read one day stale, which is
what lets the day loop step each tile once.

**Conservation is restated, not weakened.** Per tile, `sum(absorbed) + floor ==
incident` still holds exactly — shading only changes what `incident` is. Across
the grid a shaded region intercepts strictly *less* than the open sky delivers
over its area, never more, which is what
`tests/test_shading.py::test_a_shaded_region_intercepts_less_than_the_sky_delivers`
asserts.

## Grid

Milestone 1 runs `Grid(nx=1, ny=1)`, but per-tile indexing, the tile loop, the
daily shading pass and the annual dispersal pass are written for the general
case. `tests/test_grid.py::test_grid_of_nine_reproduces_a_single_tile` asserts
that a 3×3 grid with both between-tile processes off reproduces the 1×1
trajectory exactly, which is what makes that claim checkable rather than
aspirational.

Both default to off. Switching `NoDispersal` for `ExponentialKernel`, or
`NoLateralShading` for `SkyViewShading`, is all it takes to turn the vertical
slice into a spatial simulation.

## Provenance

Light geometry and layer discretisation follow the FORMIND Handbook. Soil pools,
decay rates, respiration fractions and the lignin-to-nitrogen litter split follow
CENTURY 4.0 (Parton et al.), which is the soil model GRASSMIND 3.0 itself
recodes.

## Departures from CENTURY 4.0

The pool structure, maximum decay rates, respiration fractions and target C:N
ratios are the published values and are deliberately untouched — they are what
makes this port auditable against Parton et al. Two things differ:

| Change | Why |
|---|---|
| **Atmospheric nitrogen deposition added** (`SoilColumn.add_deposition_n`, `nitrogen_deposition_kg_m2_year` = 0.002, ~20 kgN ha⁻¹ y⁻¹) | CENTURY carries such an input; this port simply had not wired one, leaving litter recycling and legume fixation as the only nitrogen inputs. Tracked separately in `cumulative_deposition_n` so it appears as its own term in `nitrogen_balance_error`. |
| **`uptake_n` is uncapped** — a deliberate non-change | A soil-side diffusion limit on daily withdrawal was implemented, measured and removed. At equilibrium it cannot change the long-run mean supply, which is set by mineralisation; it only lowered the flux and left a larger standing mineral pool to leach. Buffering against a bad day belongs on the plant side — see each vegetation module's `_take_nitrogen`. |

## Tests

```bash
uv run pytest packages/ecocore/tests -q
```
