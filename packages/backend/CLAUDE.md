# backend — conventions

FastAPI service over the coupled simulation. Read `README.md` first.

## Do not

- **Do not put ecology here.** No growth equations, no allometry, no parameter
  defaults with scientific meaning. `scenario.py` maps names onto the model
  packages; that is the whole remit.
- **Do not run a simulation on the request thread.** Runs take tens of seconds.
- **Do not estimate progress.** It comes from the `progress` callback inside
  `ecocore.run_simulation`'s daily loop.

## The schema contract

`schemas.py` and `frontend/src/types.ts` are hand-kept in sync — there is no
codegen step. Add a field in both. `packages/backend/tests/test_api.py` is what
catches drift; keep it thorough rather than adding a build step.

Validation bounds in `Field(...)` are the API's only defence against a scenario
that would run for hours. Keep `years`, `nx`, `ny` bounded.

## Scenario scope

Three scopes, and a field belongs to exactly one: region (`grid`, `site`,
`weather`, `vegetation`), tile type (`tile_types[].management`,
`tile_types[].vegetation`), tile (`tile_assignment`). Before adding a field, say
which it is. A per-tile soil or climate is not a new field, it is a second site —
`ecocore` guarantees one soil column and one light profile per tile, and the
scenario shape is what stops the API from promising otherwise.

There is no region-wide `management` any more. If you add one back you have two
sources of truth for what happens on a tile.

`tile_assignment` is validated, not repaired: wrong length or an unknown id is a
`422`. Padding a short assignment would run a scenario the client did not
describe.

## PFT overrides

`scenario._apply_overrides` uses `dataclasses.replace`, so the module-level
`DEFAULT_TREE_PFTS` / `DEFAULT_GRASS_PFTS` are never mutated. Do not mutate them
— they are shared across every request in the process.

## Job store

Every write opens its own SQLite connection under a lock, because writes come
from executor threads. If you swap the backend, keep `JobStore`'s method surface
(`submit`, `status`, `results`, `profiles`, `list_jobs`) — `app.py` depends on
nothing else.

Failures are captured as a truncated traceback in the `error` column and surfaced
through `GET /api/simulations/{id}`; do not let an exception escape `_run`, or
the job stays `running` forever.
