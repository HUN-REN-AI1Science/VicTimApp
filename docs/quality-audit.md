# Quality audit

Snapshot of `main` at commit `03e6ea1`. Every finding below was opened and
confirmed against the code or a command run on that commit; leads from an initial
survey that did not hold up are listed at the end.

## Baseline

| Check | Result |
|---|---|
| `uv run pytest` | 80 collected, 78 pass, 2 fail, 84 s (README says "~4 min") |
| Red tests | `test_abandoned_grassland_is_invaded_by_trees` (trees already present at year 15), `test_management_prevents_woody_encroachment[grazed]` (grazed sward 0.0176 kgC m-2, test wants > 0.02) |
| `ruff check` (repo config) | 44 findings, 41 auto-fixable (unsorted `__all__`/imports, quoted annotations, 3 unused imports) |
| `mypy packages` | 6 errors, 3 files (see B3) |
| `npm run typecheck` | clean |
| `npm run build` | 52.4 kB gzipped JS (matches `frontend/CLAUDE.md`) |

## A. False or stale statements

- **A1. `validation/README.md` does not exist** but is cited in 11 places
  (`README.md:56,70,100,115`, `CLAUDE.md:72`, `packages/*/README.md`,
  `formind/model.py:20`, `grassmind/model.py:19`, `formind/pft.py:11`).
  `.gitignore:28` excludes `validation/`, so no clone can ever have it. The docs
  tell the reader to consult it "before quoting any figure".
- **A2. `backend/schemas.py:4`** says the frontend generates its TypeScript types
  from the OpenAPI schema; `frontend/src/types.ts:4` says they are hand-written.
  The latter is true.
- **A3. `README.md:100`** says "~4 min"; measured 84 s.
- **A4. Leftover dispersal wording** after the grid removal: `CLAUDE.md:39`,
  `packages/ecocore/CLAUDE.md:41` (annual processes "and dispersal"), and
  history-narrating comments about `NoDispersal` on a "1x1 grid" in
  `ecocore/simulation.py:5` and `ecocore/tests/test_simulation.py:71,74`.
- **A5. `ecocore/CLAUDE.md`** says light conservation holds "exactly"; the tests
  assert `rel=1e-9` (`test_light.py:26,42,88`). Machine precision, not exact.

## B. Rule violations

- **B1. Provenance.** CLAUDE.md requires every process-module docstring to cite
  its source. No citation in any of `grassmind/{allometry,growth,management,
  model,mortality,pft,recruitment}.py`, `formind/recruitment.py`,
  `ecocore/{disturbance,simulation,tile,weather}.py`. `grassmind/growth.py`
  mentions FORMIND and "the published formulation" but names no paper. This
  matters most for GRASSMIND, whose licence the provenance rule exists to avoid.
  *Scientific: needs the correct references; do not guess them.*
- **B2. Timestep contract.** `grassmind/growth.py:114-115` divides by literal
  `365.0` instead of `DAYS_PER_YEAR` (numerically equal today).
- **B3. mypy errors that are real.**
  - `backend/runner.py:100,188`: returns `JobStatus | None` where `JobStatus` is
    declared; a missing job id can yield `None` to the caller.
  - `backend/scenario.py:134,149`: `ForestModule` does not satisfy
    `VegetationModule`, and `dbh_histogram` is not on that protocol.
  - `formind/model.py:350-351`: `layered_space_limitation` is typed
    `list[tuple[object, ...]]` but called with `int` keys.
- **B4. Type hints and docstrings** (global rule: all functions). Of 176
  functions: 71 lack a docstring (backend 21, ecocore 23, grassmind 17, formind
  10; dunders excluded) and 29 have incomplete hints (formind 16, grassmind 10,
  backend 3). Untyped `p` (the PFT) is the bulk.

## C. Slop and duplication

- **C1.** `N_RESERVE_DAYS = 60.0` defined twice (`formind/model.py:55`,
  `grassmind/model.py:71`). It is the repo's most load-bearing parameter; two
  copies can drift. *Moving it is a calibration-adjacent change: decide first.*
- **C2.** Function-local `import math` twice in `grassmind/model.py:530,594`.
- **C3.** Name collision in `grassmind/model.py:576-577`: `harvest_c` is annual
  per-m2, `cumulative_harvest_c` a running total reusing the stem.
- **C4.** `grassmind/model.py` repeats `formind/model.py`'s `_return_to_soil`,
  `_apply_mortality`, `_offer_seeds`, `_merge_cohorts`, `_take_nitrogen`; one
  docstring says "same purpose as formind". A shared helper may only live in
  `ecocore` and only if it contains no species biology.
- **C5.** Dead-looking exports to check before removing:
  `DEFAULT_HEIGHT_AXIS_M` (`StandProfile.tsx:29`), `Series` (`Charts.tsx:12`).

## D. Test quality

- **D1. Calibration encoded as assertions**, against "qualitative only":
  `test_forest.py:35-38`, `test_grassland.py:71,83`, `test_coupling.py:90-93`.
  Both red tests are of this kind.
- **D2. Weak assertions:** `> 0.0` (`test_coupling.py:141,143`), `> before`
  (`test_grassland.py:100-110`), a ratio that passes on a collapsed sward
  (`test_grassland.py:59-63`).
- **D3. No tests** for `backend/runner.py`, `backend/scenario.py`,
  `ecocore/{weather,disturbance,cohort}.py`, mortality/recruitment modules. No
  frontend tests.
- **D4.** `types.ts` has `ParameterPayload`, `ParameterSpec`, `ManagementPreset`
  with no pydantic counterpart, so contract tests cannot guard them.

## E. Tooling

No ruff rule selection, no ruff/mypy in dev dependencies, no CI, no pre-commit,
no eslint, no coverage. `requires-python >= 3.12` throughout.

## Survey leads that did NOT hold up

- `grassmind/growth.py` "analytically integrated" claim: **true**
  (`plant_photosynthesis` uses the closed form).
- Grass shade mortality "from the shared profile": **true**
  (`grassmind/model.py:216` sets `light_fraction`, `:443` uses it).
- `frontend/CLAUDE.md` "~52 kB gzipped": **true**.
- Frontend ecology violations: none; `TilePanel.tsx:106,110` are display-only
  unit conversions, which `frontend/CLAUDE.md` allows.
- Boundary rules (no formind<->grassmind import, one `LightProfile`/`SoilColumn`
  per tile): **no violations found.**

## Not examined

Scientific correctness of parameter values, and the cause of the negative forest
NPP (tracked in #1 / PR #7).
