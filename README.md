# Forest–Grassland Digital Twin

A browser-based simulation of how one site evolves over time under a management
regime, driven by ports of two scientifically sound open-source ecological
process models:

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

**The tile has exactly one vertical light profile and exactly one soil column.**

Running a forest model and a grassland model side by side and blending their
outputs by cover fraction double-counts light and water: two independent carbon
balances over the same ground produce more total production than the site
receives. Everything in `packages/ecocore` exists to make that impossible, and
`tests/test_coupling.py::test_absorbed_light_never_exceeds_incident_light` fails
if it is ever violated.

Three channels couple the models, all of them physical:

1. **Light** — trees and grass deposit leaf area into the same layer stack, so
   grass receives only radiation transmitted through the canopy above it.
2. **Soil water and mineral nitrogen** — one column both modules draw from and
   return litter to. Legume fixation raises nitrogen available to the trees.
3. **Disturbance** — mowing and grazing are broadcast to *every* module, so a
   mower destroys tree saplings as well as cutting grass.

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
packages/ecocore/     coupling substrate: light, soil, weather, tile, driving loop
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
soil column are shared *state between* them, within one tile. Putting them in
either model would force a circular dependency or a duplicate — and a duplicate
is exactly the double-counting failure above.

## Running it

```bash
uv sync                                        # Python workspace
uv run uvicorn backend.app:app --reload        # http://127.0.0.1:8000

cd frontend && npm install && npm run dev      # http://localhost:5173
```

Vite proxies `/api` to port 8000, so no CORS setup is needed in development.

Open <http://localhost:5173>. It starts on 90 years of abandoned management on
bare ground. Edit the site, weather, management or initial vegetation in the
sidebar; press **Run**. A finished run gets a shareable `?run=<id>` URL.

### Tests

```bash
uv run pytest                    # everything (~4 min; 78 pass, 2 fail — see validation/)
uv run pytest -m "not slow"      # fast subset
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

The tile runs ~250 simulated years in ~30 s; a 90-year run is ~20 s. Light
resolution is ~40% of that time. This is why the API is job-and-poll rather than
synchronous: a long run routinely outlasts an HTTP timeout.
