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

## StepContext

The only thing a vegetation module may read or mutate during a day. Keep it
narrow — it is what stops modules from reaching each other. Adding a field that
lets one model see another's state defeats the design; add a shared *resource*
instead.

## diagnostics(area_m2)

Every value a module returns is per m² of ground. This was once inconsistent and
produced charts wrong by a factor of the tile area.
