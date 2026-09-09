# frontend

React + TypeScript + Vite viewer for the coupled simulation. It renders results;
it runs no ecology.

## Layout

Mirrors the FORMIND/GRASSMIND desktop convention and the BioDT prototype digital
twin: **configuration on the left, the stand picture in the centre, output charts
along the bottom.** A single time scrubber drives every view, so the stand
diagram, the map and the chart cursors always describe the same simulated year.

## Where a thing is edited

Three places, and which one a parameter lives in is the design rather than a
layout choice:

| Place | Holds | Because |
|---|---|---|
| **Sidebar** | grid, soil, weather, seed rain, tree and grass PFTs | true of the whole region — one climate, one soil, one set of species |
| **Region tab** | which land use each tile has, and that land use's management and initial vegetation | can differ between tiles, and is only legible beside the map showing *which* tile |
| **Tile tab** | one tile's outputs | belongs to a single tile's soil column and light profile |

A tile's parameters are the parameters of its **type**. Twenty-five tiles are a
handful of land uses and an assignment, not twenty-five forms, so editing
"meadow" edits every meadow at once — `TileTypeEditor` says so where the edits
happen, because it is the one thing about this design that can surprise. Every
tile always has a type: `lib/tiles.ts::normaliseAssignment` runs inside `App`'s
single `patch()`, so resizing the grid or deleting a type cannot leave a tile
without a land use.

## Two tabs, not one per tile

With more than one tile there is no such thing as "the" charts: every output
belongs to a single tile, which has its own soil column and its own light
profile, and a region-wide average would hide exactly the spatial pattern the 2D
grid exists to produce. So the centre is a tab strip:

| Tab | Shows |
|---|---|
| **Region** | the map — by land use, or by any recorded variable once a run exists — and the editor for the selected tile |
| **Tile (x, y)** | that tile's stand structure, scalar readouts and six charts (`TilePanel`) |

Two entries rather than one per tile: a 16×16 region is 256 tiles, and a strip of
257 tabs is a list, not a selector. The map is the selector, and the Tile tab is
the detail view of whatever it has selected. Clicking the map selects without
switching tabs, so drawing a region does not throw the user out of it.

The Region tab exists **before** a run, coloured by land use. It used to appear
only once a job finished, which made every scenario look like a single tile right
up to the moment it completed. Output colours the map only while the results
still describe the region on screen; edit the grid after a run and the map falls
back to land use rather than drawing a 9-tile run over 25 squares.

Only the selected tile's `ProfileRecord[]` is fetched; every tile's numeric series
already arrives with the results, so switching tiles costs one request at most and
scrubbing time costs none.

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
