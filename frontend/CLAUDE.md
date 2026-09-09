# frontend — conventions

React + TypeScript + Vite. Read `README.md` first.

## Do not

- **Do not compute ecology here.** No unit conversions that change meaning, no
  derived quantities the model should own. If a chart needs a number, add it to a
  module's `diagnostics()` and to `src/types.ts`.
- **Do not add a charting or UI framework** without a reason the SVG components
  cannot meet. The current build is ~52 kB gzipped in total.
- **Do not hard-code PFT parameter names in forms.** `ParameterForm` is driven by
  the schema the backend serves; keeping it generic is what makes a Python-side
  parameter addition free.

## Units

Everything the API returns is **per m² of ground**. Convert for display only
(stems ha⁻¹, gC m⁻²) and label the unit in the chart heading. Never convert on
the way *into* a comparison.

## Types

`src/types.ts` mirrors `backend/schemas.py` by hand. Update both together. The
backend contract tests catch drift.

## Styling

Plain CSS with custom properties in `src/styles.css`; no framework. The palette
is deliberately muted so the PFT colours — which come from the backend and match
the models' own conventions — carry the meaning.

PFT colours are served by the API (`colour` on each PFT). `TilePanel` reads the
served value and falls back to its own map only for a PFT the backend did not
describe; prefer the served value when adding a chart.

## Tabs

`App` owns `activeTab`, one of `"region"` and `"tile"`. Two entries, not one per
tile — 16×16 would be 257 tabs. **Do not add a tab per tile back.** The map is
the selector; `tile` is the selection; the Tile tab is its detail view.

`TilePanel` renders one tile and takes only that tile's data. Do not give it the
whole results payload and let it index in — a panel that can see every tile is
one refactor away from plotting a region-wide average, which would hide the
spatial pattern the 2D grid exists to produce.

## Where a parameter's form goes

- **Region-wide** (grid, soil, weather, seed rain, PFTs) → `Sidebar`.
- **Per tile** (land use, and its management and initial vegetation) →
  `TileTypeEditor`, on the Region tab, scoped to the selected tile.

Do not move a per-tile control into the sidebar. A form that changes one tile is
only legible next to the picture of which tile it changes, and the sidebar has no
selection to scope itself to.

`ScenarioConfig` has no `management` field any more; a schedule belongs to a tile
type. If you find yourself adding a region-wide management setting, you are
adding a second source of truth for what happens on a tile.

## Tile assignment

`tile_assignment` is a flat row-major list of type ids, one per tile, and **every
tile must have one**. `lib/tiles.ts::normaliseAssignment` is called from `App`'s
single `patch()` — that placement is what makes it an invariant rather than a
convention. Do not normalise at the call sites instead; resizing the grid,
deleting a type and loading a scenario would each have to remember separately.

## State

Single `ScenarioConfig` in `App`, edited through `patch()` which `structuredClone`s
before mutating. Do not mutate config objects in place — the deep clone is what
keeps React's change detection honest for nested fields like
`vegetation.tree_pft_overrides`.
