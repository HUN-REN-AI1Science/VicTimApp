# grassmind — invariants

Port of the GRASSMIND grassland model. Read `README.md` first.

## Do not

- **Do not import `formind`.** Trees reach this module only as less light and
  less water, through `ecocore`.
- **Do not compute light here.** It arrives in `ctx.light`.
- **Do not apply management directly from `self.management`.** Emit
  `Defoliation` events in `emit_disturbances` and act on `ctx.disturbances`. If
  mowing is applied privately, the forest module never sees it and the model
  concludes that every hay meadow becomes woodland. Fertilisation is the
  exception — it acts on the soil, not on standing biomass.

## Shoot carbon is the state

`GrassCohort.shoot_c` and `root_c` are the state; `leaf_c` / `stem_c` are derived
by `sync_biomass` and must be re-synced after any change. An individual is a
tiller: per-plant masses are ~10⁻⁴ kgC and densities are hundreds per m². If a
change makes per-plant mass reach grams, something has broken the size cap.

## Three processes that must not be "simplified away"

Each was added because the model was demonstrably wrong without it:

1. **Remobilisation** (`remobilisation_rate`) — regrowth after cutting is paid
   for from root reserves, not from current photosynthesis. Remove it and every
   mowing regime destroys the sward.
2. **Root allocation** (`root_fraction` ≈ 0.62) — the reserve pool. Same failure
   if under-sized.
3. **Clonal tillering** (`max_shoot_c` and `_tiller`) — surplus growth becomes
   new individuals. Remove the cap and carbon piles into a few tree-sized
   "plants".

## Load-bearing parameters

- `maintenance_respiration` — sets the ceiling on standing biomass (≈ NPP / rate).
- `MowingEvent.woody_kill_height_m` — decides whether management can stop tree
  invasion at all.
- `ESTABLISHMENT_EFFICIENCY` in `recruitment.py` — lumps germination, seedling
  survival and clonal tillering; tuned so an unshaded sward equilibrates at a few
  thousand tillers per m².

## Nitrogen fixation

Legume fixation goes to `soil.add_fixed_n`, not `add_fertiliser_n`. They are
tracked separately because fixation is a new input from the atmosphere and
fertiliser is a management input, and both appear as distinct terms in
`nitrogen_balance_error`.

## Cohort merging

Logarithmic in shoot mass, because a seedling and a mature tiller differ by
orders of magnitude. Without merging, annual recruitment grows the cohort list
without bound.

## Adding a PFT parameter

Add the field to `GrassPFT` **and** an entry in the `groups` and `units` maps in
`grass_pft_schema()`. The UI form is generated from that schema.
