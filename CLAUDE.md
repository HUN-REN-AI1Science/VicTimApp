# Repository conventions

A coupled FORMIND (forest) + GRASSMIND (grassland) simulation with a FastAPI
backend and a React frontend. Read `README.md` first for what the project is.

## The invariant everything else serves

**One vertical light profile and one soil column per tile, shared by every
vegetation module.** Any change that gives a model its own light or its own soil
double-counts the resource and invalidates the whole model. If you find yourself
adding a second `LightProfile` or `SoilColumn` inside a tile, stop.

`tests/test_coupling.py::test_absorbed_light_never_exceeds_incident_light` is the
automated guard. Do not weaken it.

## Package boundaries

- `formind` and `grassmind` **must never import each other.** Cross-model effects
  travel through `ecocore` only: shared light, shared soil, broadcast
  disturbances. If a coupling seems to need a direct import, it is being modelled
  in the wrong place.
- `ecocore` contains **no species biology** — no allometry, no photosynthesis, no
  PFTs. It owns the resources the models compete for and nothing else.
- `backend` contains **no ecology**. It maps a scenario description onto an
  `ecocore.Grid` and serves results.

## Units

Declared in `packages/ecocore/src/ecocore/units.py`. Two rules:

- Cohort carbon compartments are **per individual** (kgC); multiply by `n`.
- Every `diagnostics(area_m2)` value is **per m² of ground**. This was once
  inconsistent and produced charts wrong by a factor of the tile area — do not
  reintroduce mixed units.

## Timestep contract

Daily for water, carbon and light; annual for mortality, recruitment, cohort
merging and seed dispersal. FORMIND upstream steps annually and GRASSMIND daily,
so this reconciliation is the most likely place for a silent rate bug. A rate
given per year must be divided by `DAYS_PER_YEAR` at the point of use, not
earlier.

## Adding a parameter

Add it to the `TreePFT` / `GrassPFT` dataclass **and** to the `groups`/`units`
maps in that module's `*_pft_schema()`. The backend serves the schema and the
frontend builds its form from it, so those two edits are the whole job — no
frontend change is needed. `test_parameter_schema_is_complete` fails if a schema
entry names a field the PFT does not have.

## Provenance

Ported from published equations, never from upstream source. Every process module
docstring names the paper or handbook section it implements. Keep that up to date
when you change a formulation — it is what makes the port auditable and what
keeps the repository clear of GRASSMIND's EUPL copyleft.

## Calibration is not validated

Parameter values are literature-typical starting points, not a fitted set. If you
change one, say why in its docstring and note the effect on the behaviour tests.
Several parameters are load-bearing for qualitative behaviour and are documented
as such in place — `seedling_mortality`, `maintenance_respiration`,
`woody_kill_height_m`, `cd0`, `N_RESERVE_DAYS`. Changing them changes what the
model concludes.

`N_RESERVE_DAYS` is the worst of them and the newest: at 60 days an abandoned
tile is invaded by trees, at 90 days it never is. It is also a parameter this
port invented rather than ported, so it has no literature value to appeal to.
Two behaviour tests are currently red and it would be easy to make them pass by
widening the reserve — do not. See `validation/README.md`, "Nitrogen limitation".

## Tests

`uv run pytest -m "not slow"` for the fast loop; the full suite runs multi-decade
simulations and takes minutes. Behaviour tests assert *qualitative* patterns
(succession happens, mowing prevents invasion) rather than numbers, so that
recalibration does not require rewriting them. Keep them that way.

## Development process

Work flows in one direction:

**GitHub issue → implementation with Claude Code → pull request → human review →
iteration if needed → merge.**

Every change starts as a GitHub issue, so the reasoning behind it is recorded
before any code is written. Implementation happens with Claude Code against that
issue. The result goes up as a pull request — nothing lands on `main` directly.
A human reviews the PR; review comments are addressed in further iterations on
the same branch, and the PR is merged only once that review is satisfied.
