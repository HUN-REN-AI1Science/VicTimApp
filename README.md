# Forest–Grassland Digital Twin

A browser-based simulation of how a 2D tiled region evolves over time, driven by
ports of two scientifically sound open-source ecological process models:

| Model | Represents | Upstream | Licence upstream |
|---|---|---|---|
| **FORMIND** | Individual-based forest gap dynamics | UFZ Leipzig, [formind.org](https://formind.org/model/formind/formind/) | site terms & conditions |
| **GRASSMIND** | Individual-based species-rich grassland | UFZ Leipzig, [BioDT/uc-grassland-model](https://github.com/BioDT/uc-grassland-model) | EUPL-1.2 |
| **CENTURY 4.0** | Soil carbon and nitrogen | Parton et al. | — |

The pairing is not arbitrary. GRASSMIND was *derived from* FORMIND, and
GRASSMIND 3.0's own README states it "incorporates recoded functions from
FORMIND (forest model) and CENTURY 4.0 (soil model)." Both share one
architecture — individual/cohort-based, competition resolved through a
Lambert–Beer light profile, growth driven by a GPP → respiration → NPP carbon
balance — so coupling them is a matter of letting them share resources rather
than reconciling two foreign formulations.

## The one rule the design exists to enforce

**Every tile has exactly one vertical light profile and exactly one soil column.**

Running a forest model and a grassland model side by side and blending their
outputs by cover fraction double-counts light and water: two independent carbon
balances over the same ground produce more total production than the site
receives. Everything in `packages/ecocore` exists to make that impossible, and
`tests/test_coupling.py::test_absorbed_light_never_exceeds_incident_light` fails
if it is ever violated.

Three channels couple the models *within* a tile, all of them physical:

1. **Light** — trees and grass deposit leaf area into the same layer stack, so
   grass receives only radiation transmitted through the canopy above it.
2. **Soil water and mineral nitrogen** — one column both modules draw from and
   return litter to. Legume fixation raises nitrogen available to the trees.
3. **Disturbance** — mowing and grazing are broadcast to *every* module, so a
   mower destroys tree saplings as well as cutting grass.

Two more cross tile boundaries, which is what makes a region more than N
independent columns:

4. **Seed dispersal** — an exponential seed shadow, resolved once a year, so a
   forested tile seeds the grassland next to it.
5. **Lateral shading** — a sky view factor computed from the neighbours' canopy
   heights, resolved once a day, so a tile beside a 30 m canopy does not receive
   open-sky irradiance however empty its own profile is.

Both default to off, so a multi-tile run reproduces the single-tile trajectory
until one is switched on — see `packages/ecocore/README.md`. The scenario the UI
opens on turns both on, because neither does anything visible in twenty-five
identical columns.

## What a tile is

A tile carries the region's soil, the region's weather and the region's plant
functional types. What it carries of its own is a **land use**: a management
schedule and the vegetation standing on it at year zero. Those two are the only
things that legitimately differ between two tiles of one region — a tile with
its own soil column would be a second site, not a second land use.

So a region is a short list of land-use types and an assignment of tiles to them.
Twenty-five tiles are five types and a map, not twenty-five forms, and editing
*meadow* edits every meadow at once. The map in the browser is where that
assignment is drawn, and it is also the tile selector, so the region is a picture
from the moment it is configured rather than from the moment a run finishes.

## What it reproduces

From a 90-year run of the same site under three regimes, with nothing changed but
management:

| Regime | Year 90 outcome |
|---|---|
| Abandoned | Invaded by trees; closed forest, grass eliminated |
| Extensive meadow (1 cut/yr) | Grassland indefinitely |
| Pasture (season-long grazing) | Grassland indefinitely, shorter sward |

> **The numbers here are currently unreliable.** Two behaviour tests are red and
> the nitrogen cycle is mis-calibrated: invasion arrives around year 15 rather
> than year 40, and standing crop is half to a third of what it should be. The
> direction of each pattern survives; the timing and magnitude do not. See
> `validation/README.md`, "Nitrogen limitation", before quoting any figure.

None of this is scripted. Woody encroachment emerges because seedlings survive
the sward, cross breast height, and then shade the grass below its
mortality threshold through the shared light profile.

## Repository layout

```
packages/ecocore/     coupling substrate: light, soil, weather, tile, grid, dispersal
packages/formind/     forest process model port
packages/grassmind/   grassland process model port
packages/backend/     FastAPI service (job-and-poll)
frontend/             React + TypeScript + Vite viewer
validation/           reference outputs and comparison notes
tests/                cross-package integration tests
```

Each package has its own `README.md` (what it models, units, provenance) and
`CLAUDE.md` (invariants not to break).

`ecocore` is a fifth package beyond the two models because the light profile and
soil column are shared *state between* them. Putting them in either model would
force a circular dependency or a duplicate — and a duplicate is exactly the
double-counting failure above.

## Running it

```bash
uv sync                                        # Python workspace
uv run uvicorn backend.app:app --reload        # http://127.0.0.1:8000

cd frontend && npm install && npm run dev      # http://localhost:5173
```

Vite proxies `/api` to port 8000, so no CORS setup is needed in development.

Open <http://localhost:5173>. It starts on a 5×5 region with a wooded edge, three
columns of abandoned field and a mown strip. Click a tile on the **Region** tab to
change its land use or edit that land use's management; open **Tile** for its
outputs; press **Run**. A finished run gets a shareable `?run=<id>` URL.

### Tests

```bash
uv run pytest                    # everything (~5 min; 104 pass, 2 fail — see validation/)
uv run pytest -m "not slow"      # fast subset (~2 min)
cd frontend && npm run typecheck
```

## Provenance and licensing

The model packages are **ported from published process descriptions** — the
FORMIND Handbook, the GRASSMIND papers, the BioDT prototype digital twin
documentation, and Parton et al. for CENTURY — **not from the upstream source
code**. Equations are not copyrightable, so this repository carries no copyleft
obligation from GRASSMIND's EUPL-1.2 or from FORMIND's site terms. Every ported
module names the process description it implements in its docstring.

This is a port, not a redistribution, and it is **not calibrated against the
reference implementations**. See `validation/README.md` for what has and has not
been checked, and each model package's README for known simplifications.

## Performance

A single tile runs ~250 simulated years in ~30 s; a 90-year coupled run is
~20 s. Light resolution is ~40% of that time. This is why the API is
job-and-poll rather than synchronous: runs routinely outlast an HTTP timeout.

Cost is linear in tiles — every tile is simulated in full — so the 5×5 scenario
the UI opens on is about twenty-five times a single tile. Shrink the region or
the number of years before iterating on anything else.
