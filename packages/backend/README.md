# backend

The FastAPI service that drives the coupled simulation. **Holds no ecology.** It
turns a scenario description into an `ecocore.Tile`, runs it off the request
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
| `GET` | `/api/simulations/{id}/results` | Numeric time series |
| `GET` | `/api/simulations/{id}/profile` | Vertical stand and sward structure |

`results` returns `409` while a run is unfinished and `500` if it failed.

### Why the parameter endpoints matter

They serve a *description* of every adjustable parameter — name, group, unit,
default, type — so the browser builds its configuration forms generically.
Adding a field to `TreePFT` and its schema map makes it appear in the UI with no
frontend change. `test_parameter_schema_is_complete` fails if a schema entry
names a field the PFT does not have.

### How a scenario is scoped

`ScenarioConfig` is flat: `site`, `weather`, `management` and `vegetation` each
describe the one tile a run simulates. There is no per-tile indirection to
resolve — `scenario.build_tile` reads the config once and builds the tile it
describes.

### Why the default scenario is not the schema default

`GET /api/scenarios/default` serves 90 years of abandoned management on bare
ground — the one regime whose outcome changes over the run, so it is the most
legible thing to show on first load. The schema defaults themselves stay a
short, cheap run, so a `POST` that omits fields still gets something runnable
rather than an implicit long simulation.

### Why profiles are a separate endpoint

Stand and sward profiles are nested and large enough to dominate a results
payload. `runner.JobStore._split` separates them at storage time.

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
