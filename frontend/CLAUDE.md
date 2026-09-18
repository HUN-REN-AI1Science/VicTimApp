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

## One view, no tabs

There is one tile, so there is nothing to select and nothing to switch between.
`App` renders `Sidebar` and `TilePanel` directly — do not add a tab per tile, or
a tab at all, back in.

## Where a parameter's form goes

Everything — site, weather, management, initial vegetation, seed rain, PFTs —
lives in `Sidebar`. There is only one scope now, so there is no second place a
form could legitimately go.

## State

Single `ScenarioConfig` in `App`, edited through `patch()` which `structuredClone`s
before mutating. Do not mutate config objects in place — the deep clone is what
keeps React's change detection honest for nested fields like
`vegetation.tree_pft_overrides`.
