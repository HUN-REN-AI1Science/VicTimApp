# ecocore — invariants

The shared substrate. Everything here is load-bearing for the coupling.

## Do not

- **Do not add species biology.** No allometry, no photosynthesis, no PFTs, no
  growth forms. If a change needs to know what a tree is, it belongs in `formind`.
- **Do not let a tile hold more than one `LightProfile` or `SoilColumn`.** That is
  the double-counting failure the whole package exists to prevent.
- **Do not import `formind` or `grassmind`.** `ecocore` is the bottom of the
  dependency graph.

## Light module

`compute_light` must keep `sum(absorbed) + floor == incident` exactly.
`tests/test_light.py` checks this across configurations; if you change the
attenuation maths, that identity is the acceptance criterion.

Lateral shading does not weaken that identity, and must not be allowed to. A
shading kernel changes only what `incident` *is* — one scalar per tile, applied
before `resolve` — so the per-tile identity is untouched. The grid-level
statement is the one it does change, and `tests/test_shading.py` owns it: a
shaded region intercepts strictly less than the open sky delivers over its area,
never more. Any future between-tile light exchange that could *raise* a tile's
incident above open sky is a double-count and belongs nowhere near this package.

It is vectorised because it runs once per tile per simulated day. Before
optimising further, note that ~40% of total runtime is here, and that absorbed
*fractions* depend only on geometry, not on incident irradiance — that linearity
is the obvious next speedup, but only if geometry caching stays exact.

`CanopyElement` validates its own geometry in `__post_init__`. Keep it: a crown
with `top < base` or `k` outside `(0, 1]` produces silently wrong light rather
than an error.

## Soil module

Carbon and nitrogen conservation is asserted to machine precision. Every transfer
must move carbon and nitrogen together and account respiration explicitly —
`_transfer` is the only place pools should change during decomposition.

Every new nitrogen source or sink needs its own `cumulative_*` counter **and** a
term in `nitrogen_balance_error`, or the audit silently stops being an audit.

## Timestep contract

Daily for water, carbon, light. Annual for mortality, recruitment, cohort merging
and dispersal. FORMIND steps annually upstream and GRASSMIND daily, so this
reconciliation is where a silent rate bug is most likely. Annual rates are
divided by `DAYS_PER_YEAR` at the point of use.

## Cross-tile state

`Tile.canopy_top_m` is the one piece of a tile's state a neighbouring tile may
read, and only through `shading.LateralShading`, which reduces it to a scalar sky
view factor. A scalar height is not species biology — this package still never
learns what grew to it.

Keep it that way. A kernel that reached for a neighbour's cohorts, or a
`StepContext` that carried a neighbour list, would put spatial ecology inside
`ecocore` and let a module see another tile's model directly. Cross-tile effects
travel as resources, exactly as cross-model effects do within a tile.

Both between-tile processes default to off (`NoDispersal`, `NoLateralShading`).
That default is what keeps
`tests/test_grid.py::test_grid_of_nine_reproduces_a_single_tile` a meaningful
regression guard — do not make either one always-on.

## StepContext

The only thing a vegetation module may read or mutate during a day. Keep it
narrow — it is what stops modules from reaching each other. Adding a field that
lets one model see another's state defeats the design; add a shared *resource*
instead.

## diagnostics(area_m2)

Every value a module returns is per m² of ground. This was once inconsistent and
produced charts wrong by a factor of the tile area.
