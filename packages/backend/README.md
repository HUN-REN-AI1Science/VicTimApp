# backend

The FastAPI service that drives the coupled simulation. **Holds no ecology.** It
turns a scenario description into an `ecocore.Grid`, runs it off the request
thread, and serves progress and results to the browser.

## Why job-and-poll

A century-scale coupled run takes tens of seconds — far past a sensible HTTP
timeout — so `POST /api/simulations` returns `202` immediately with an id and the
frontend polls. This mirrors how the BioDT grassland prototype digital twin
offloads its runs. Progress is reported from a callback **inside the daily loop**,
so it is a real day count rather than an estimate.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness |
| `GET` | `/api/parameters/{model}` | Parameter **schema** + current defaults (`formind` \| `grassmind`) |
| `GET` | `/api/management/presets` | The four management regimes, with their events |
| `GET` | `/api/scenarios/default` | A ready-to-run scenario |
| `POST` | `/api/simulations` | Start a run → `202` + `JobStatus`, `Location` header |
| `GET` | `/api/simulations` | Recent jobs, newest first |
| `GET` | `/api/simulations/{id}` | Status and progress |
| `GET` | `/api/simulations/{id}/results` | Numeric time series per tile |
| `GET` | `/api/simulations/{id}/profile?x=&y=` | Vertical stand and sward structure |

`results` returns `409` while a run is unfinished and `500` if it failed.

### Why the parameter endpoints matter

They serve a *description* of every adjustable parameter — name, group, unit,
default, type — so the browser builds its configuration forms generically.
Adding a field to `TreePFT` and its schema map makes it appear in the UI with no
frontend change. `test_parameter_schema_is_complete` fails if a schema entry
names a field the PFT does not have.

### How a scenario is scoped

`ScenarioConfig` splits three ways, and the split is the shape of the model
rather than of the form:

| Scope | Fields | Why there |
|---|---|---|
| region | `grid`, `site`, `weather`, `vegetation` | one climate, one soil, one set of PFTs. A tile with its own soil column would be a second site, and `ecocore` guarantees exactly one column per tile |
| tile type | `tile_types[]` — `management` and initial `vegetation` | the only two things that legitimately differ between two tiles of one region |
| tile | `tile_assignment[]` — one type id per tile, row-major | a tile is nothing but a land use and a position |

`tile_assignment` may be empty, meaning every tile takes `tile_types[0]`; that is
how a client which has never heard of tile types still gets a uniform, runnable
region. A *partial* assignment is rejected with `422` rather than padded — filling
in the tiles a caller forgot would run a different scenario than the one they
described.

`scenario.build_grid` builds one `ManagementSchedule` per type, not per tile:
schedules are read and never mutated during a run, so twenty-five meadow tiles
share one.

### Why the default scenario is not the schema default

`GET /api/scenarios/default` serves a 5×5 region with a wooded edge, a mown strip
and both between-tile fluxes on — a demonstration, because neither flux does
anything visible in twenty-five identical columns. The `GridConfig` field
defaults stay 1×1 with both fluxes off: a `POST` that omits `grid` must not
silently buy twenty-five times the work, or a different physics, and
`ecocore`'s grid-reproduces-a-single-tile guard depends on off being off.

### Why profiles are a separate endpoint

Stand and sward profiles are nested and large enough to dominate a results
payload, and the map view does not need them. `runner.JobStore._split` separates
them at storage time.

## Modules

| Module | Role |
|---|---|
| `schemas.py` | Pydantic request/response models — the contract with the frontend |
| `scenario.py` | The only place that maps API vocabulary onto the three model packages |
| `runner.py` | SQLite-backed job registry and thread-pool executor |
| `app.py` | Routes |

`JobStore` is a deliberately small surface — submit, status, results, profiles,
list — so swapping the thread pool for Celery, RQ or an HPC queue touches one
file. Jobs live in SQLite (`TWIN_DB`, default `simulations.db`) so a restart does
not lose finished results.

## Running

```bash
uv run uvicorn backend.app:app --reload     # http://127.0.0.1:8000
```

Interactive API docs at `/docs`. CORS allows `localhost:5173`; in development the
Vite proxy makes even that unnecessary.

## Tests

```bash
uv run pytest packages/backend/tests -q
```

Each test gets its own temporary SQLite file via the `client` fixture.
