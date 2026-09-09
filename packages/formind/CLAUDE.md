# formind — invariants

Port of the FORMIND forest gap model. Read `README.md` for what each module does.

## Do not

- **Do not import `grassmind`.** Ever. Grass reaches this module only as less
  light and less water, via `ecocore`. That indirection is the design.
- **Do not compute light here.** Irradiance arrives in `ctx.light`. A module that
  attenuates its own canopy separately double-counts radiation.
- **Do not add an explicit "grass suppresses seedlings" channel.** It is already
  mechanistic through the shared floor light. Adding one double-counts it.

## Diameter is the state

`TreeCohort.dbh` is the state variable; leaf, stem and root carbon are *derived*
by `sync_biomass` and must be re-synced after any change to `dbh`. Do not set the
carbon compartments directly — they will be overwritten and the tree's geometry
will silently disagree with its mass.

## Seedlings are not thin trees

Anything below breast height belongs in `self.seedlings`, tracked by **height**,
never in `self.cohorts`. `initial_dbh` is chosen so `allometry.height(initial_dbh)`
lands at ~1.3 m; `test_promotion_diameter_lands_near_breast_height` guards it. If
you change the height allometry, re-derive `initial_dbh` or seedlings will
teleport into the canopy.

## Space limitation is per layer

`mortality.layered_space_limitation` thins each height layer independently. A
"simplification" back to total crown area over patch area caps stand LAI near a
single crown's LAI and brightens the forest floor to implausible levels. It looks
like a tidy-up; it is a regression.

## Load-bearing parameters

Changing these changes what the model concludes, not just its numbers:

- `seedling_mortality` — compounds over the many years to breast height. At
  0.35 y⁻¹ abandoned grassland stays grassland forever; at 0.05 y⁻¹ a mown meadow
  cannot be maintained.
- `cd0` — crown width sets stand density, basal area and floor light.
- `initial_dbh` — see above.

Each is documented in place in `pft.py`. Say why in the docstring if you change
one, and check the behaviour tests still pass.

## Adding a PFT parameter

Add the field to `TreePFT` **and** an entry in the `groups` and `units` maps in
`tree_pft_schema()`. The backend serves that schema and the frontend builds its
form from it; no frontend change is needed.
