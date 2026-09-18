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
that would run for hours. Keep `years` bounded.

## Scenario scope

`ScenarioConfig` describes one tile: `site`, `weather`, `management`,
`vegetation`. There is only one scope, so there is no question of which a new
field belongs to — but resist adding a second soil or climate field regardless.
`ecocore` guarantees one soil column and one light profile per tile, and a
scenario shape that let two fields describe two sites would let the API promise
something the model cannot do.

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
