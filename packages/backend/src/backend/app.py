"""FastAPI application.

Job-and-poll throughout: `POST /api/simulations` returns immediately with an id,
the frontend polls `GET /api/simulations/{id}` for real progress reported from
inside the daily loop, then fetches results when the run is done.

The parameter endpoints matter more than they look. They serve a *description* of
every adjustable parameter -- name, group, unit, default -- so the browser builds
its configuration forms generically. Adding a parameter to a PFT dataclass makes
it appear in the UI with no frontend change.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from formind import DEFAULT_TREE_PFTS, tree_pft_schema
from grassmind import DEFAULT_GRASS_PFTS, ManagementSchedule, grass_pft_schema

from .runner import JobStore
from .schemas import GridConfig, JobStatus, ScenarioConfig

__all__ = ["app", "create_app"]


def create_app(database: str | None = None) -> FastAPI:
    store = JobStore(database or os.environ.get("TWIN_DB", "simulations.db"))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        store.shutdown()

    application = FastAPI(
        title="Forest-Grassland Digital Twin",
        version="0.1.0",
        summary="Coupled FORMIND/GRASSMIND simulation of a 2D tiled region.",
        lifespan=lifespan,
    )
    application.state.store = store
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------- health --

    @application.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    # --------------------------------------------------------- parameters --

    @application.get("/api/parameters/{model}", tags=["parameters"])
    def parameters(model: str) -> dict:
        """Adjustable parameters and current defaults for one model.

        `model` is `formind` or `grassmind`.
        """
        if model == "formind":
            return {
                "model": "formind",
                "schema": tree_pft_schema(),
                "pfts": [
                    {"id": p.id, "label": p.label, "colour": p.colour,
                     **{f["name"]: getattr(p, f["name"]) for f in tree_pft_schema()}}
                    for p in DEFAULT_TREE_PFTS
                ],
            }
        if model == "grassmind":
            return {
                "model": "grassmind",
                "schema": grass_pft_schema(),
                "pfts": [
                    {"id": p.id, "label": p.label, "colour": p.colour,
                     **{f["name"]: getattr(p, f["name"]) for f in grass_pft_schema()}}
                    for p in DEFAULT_GRASS_PFTS
                ],
            }
        raise HTTPException(404, f"unknown model {model!r}; expected formind or grassmind")

    @application.get("/api/management/presets", tags=["parameters"])
    def management_presets() -> list[dict]:
        """The management regimes the UI offers as one-click starting points."""
        presets = {
            "abandoned": ("Abandoned", "No management. Trees eventually take the site."),
            "extensive_meadow": ("Extensive meadow", "One late cut a year, no fertiliser."),
            "intensive_meadow": ("Intensive meadow", "Four cuts and two fertiliser applications."),
            "pasture": ("Pasture", "Season-long grazing."),
        }
        out = []
        for key, (label, description) in presets.items():
            schedule: ManagementSchedule = getattr(ManagementSchedule, key)()
            out.append(
                {
                    "id": key,
                    "label": label,
                    "description": description,
                    "mowing": [
                        {"day_of_year": e.day_of_year, "cut_height_m": e.cut_height_m,
                         "removal_fraction": e.removal_fraction,
                         "woody_kill_height_m": e.woody_kill_height_m}
                        for e in schedule.mowing
                    ],
                    "grazing": [
                        {"start_day": g.start_day, "end_day": g.end_day,
                         "intake_fraction_per_day": g.intake_fraction_per_day,
                         "return_fraction": g.return_fraction, "min_height_m": g.min_height_m,
                         "woody_kill_height_m": g.woody_kill_height_m,
                         "woody_kill_fraction": g.woody_kill_fraction}
                        for g in schedule.grazing
                    ],
                    "fertilisation": [
                        {"day_of_year": f.day_of_year, "nitrogen_kg_m2": f.nitrogen_kg_m2}
                        for f in schedule.fertilisation
                    ],
                }
            )
        return out

    @application.get("/api/scenarios/default", tags=["parameters"])
    def default_scenario() -> ScenarioConfig:
        """A ready-to-run scenario, so the UI opens with something meaningful.

        A region rather than a single tile, and a region that is not uniform: the
        model is a 2D one with two fluxes across tile boundaries, and neither of
        them does anything visible in twenty-five identical columns. This one is
        a wooded edge, three columns of abandoned field, and a mown meadow strip
        on the far side -- so seeds blow off the wood into the field, the field's
        own canopy shades what is beside it, and the meadow demonstrates that
        cutting is what stops the invasion. That is the whole model in one map.

        Everything named here is named *here* rather than in the schema defaults.
        A POST that omits `grid` still means one unshaded, non-dispersing tile:
        an API client should not silently buy twenty-five times the work, or a
        different physics, by leaving a field out.
        """
        nx, ny = 5, 5
        strip = ["forest", "abandoned", "abandoned", "abandoned", "meadow"]
        return ScenarioConfig(
            name="Wood edge and meadow",
            years=90,
            grid=GridConfig(
                nx=nx, ny=ny, dispersal="exponential", lateral_shading="sky_view"
            ),
            tile_assignment=strip * ny,
        )

    # -------------------------------------------------------- simulations --

    @application.post("/api/simulations", status_code=202, tags=["simulations"])
    def create_simulation(config: ScenarioConfig, response: Response) -> JobStatus:
        job = store.submit(config)
        response.headers["Location"] = f"/api/simulations/{job.id}"
        return job

    @application.get("/api/simulations", tags=["simulations"])
    def list_simulations(limit: int = 50) -> list[JobStatus]:
        return store.list_jobs(limit)

    @application.get("/api/simulations/{job_id}", tags=["simulations"])
    def simulation_status(job_id: str) -> JobStatus:
        status = store.status(job_id)
        if status is None:
            raise HTTPException(404, "no such simulation")
        return status

    @application.get("/api/simulations/{job_id}/results", tags=["simulations"])
    def simulation_results(job_id: str) -> dict:
        status = store.status(job_id)
        if status is None:
            raise HTTPException(404, "no such simulation")
        if status.state == "failed":
            raise HTTPException(500, status.error or "simulation failed")
        results = store.results(job_id)
        if results is None:
            raise HTTPException(409, f"simulation is {status.state}, not finished")
        return results

    @application.get("/api/simulations/{job_id}/profile", tags=["simulations"])
    def simulation_profile(job_id: str, x: int = 0, y: int = 0) -> list[dict]:
        """Vertical stand and sward structure for one tile, one entry per record.

        Served separately from the numeric series because it is nested and would
        otherwise dominate the results payload.
        """
        profiles = store.profiles(job_id, x, y)
        if profiles is None:
            raise HTTPException(404, "no profile for that simulation or tile")
        return profiles

    return application


app = create_app()
