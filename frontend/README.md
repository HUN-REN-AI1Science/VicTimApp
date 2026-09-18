# frontend

React + TypeScript + Vite viewer for the coupled simulation. It renders results;
it runs no ecology.

## Layout

Mirrors the FORMIND/GRASSMIND desktop convention and the BioDT prototype digital
twin: **configuration on the left, the stand picture in the centre, output charts
along the bottom.** A single time scrubber drives every view, so the stand
diagram and the chart cursors always describe the same simulated year.

## Where a thing is edited

One view, one scope: `Sidebar` holds site, weather, management, initial
vegetation, seed rain and the tree and grass PFTs, because all of it describes
the one tile a run simulates. `App` renders `Sidebar` beside `TilePanel`, the
tile's outputs — there is no second screen to switch to.

## The stand-structure view

`components/StandProfile.tsx` is the view worth having. It draws tree crowns and
the grass sward **in one diagram against one height axis**, because in the model
they occupy one shared light profile — the picture is the argument for the
architecture.

FORMIND is horizontally position-free within a patch, so the model has no x
coordinate to give. Positions are generated deterministically from the cohort
index, which keeps the picture stable while the user scrubs through time and is
honest that horizontal placement is illustrative, not simulated. Individuals are
sampled proportionally to cohort abundance and capped at 140, so a stand of ten
thousand seedlings still renders in one frame.

## Charts

`components/Charts.tsx` — dependency-free SVG. These reproduce the standard
FORMIND/GRASSMIND outputs (biomass through time by functional type, stem number
by diameter class) rather than offering a general charting toolkit, which is why
they are ~150 lines instead of a library.

## Generic parameter forms

`components/ParameterForm.tsx` renders whatever `GET /api/parameters/{model}`
describes. It knows nothing about `pmax` or `crown_lai`. Adding a parameter in
Python makes it appear here with no change to this file.

## Deep links

A finished run gets `?run=<id>` in the URL, and loading that URL reopens the
result without recomputing it.

## Types

`src/types.ts` mirrors `packages/backend/src/backend/schemas.py` by hand — no
codegen step. The backend's API contract tests are what keep the two in
agreement; if you add a field, add it in both places.

## Running

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api to 127.0.0.1:8000
npm run typecheck
npm run build
```

The backend must be running on port 8000. Vite proxies `/api`, so no CORS
configuration is needed in development.
