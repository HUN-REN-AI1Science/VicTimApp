/**
 * The tile ↔ type mapping, in one place.
 *
 * `tile_assignment` is a flat row-major list of type ids, one per tile. Every
 * tile must have a type — a tile with no land use is not a thing the model can
 * simulate — so the assignment is regenerated whenever the grid is resized
 * rather than being left for the user to repair. `normaliseAssignment` is called
 * from `App`'s single `patch()`, which is what makes "every tile has a type" an
 * invariant instead of a convention.
 */

import type { ScenarioConfig, TileTypeConfig } from "../types";

export const assignmentIndex = (nx: number, x: number, y: number) => y * nx + x;

/** The type id governing (x, y). Falls back to the first type, as the API does. */
export function typeIdAt(config: ScenarioConfig, x: number, y: number): string {
  const i = assignmentIndex(config.grid.nx, x, y);
  return config.tile_assignment[i] ?? config.tile_types[0]?.id ?? "";
}

export function typeAt(config: ScenarioConfig, x: number, y: number): TileTypeConfig | undefined {
  const id = typeIdAt(config, x, y);
  return config.tile_types.find((t) => t.id === id) ?? config.tile_types[0];
}

export const typeById = (types: TileTypeConfig[], id: string) => types.find((t) => t.id === id);

/**
 * Make the assignment exactly `nx * ny` long, keeping each surviving tile's type.
 *
 * `previous` is the grid the current assignment was written for. Tiles that
 * still exist keep what they had — growing a 3×3 into a 5×5 must not shuffle the
 * nine tiles already there — and tiles that are new take the first type. A type
 * that has been deleted is replaced the same way, so an assignment can never
 * name an id the backend would reject.
 */
export function normaliseAssignment(
  draft: ScenarioConfig,
  previous: { nx: number; ny: number },
): void {
  const fallback = draft.tile_types[0]?.id ?? "";
  const known = new Set(draft.tile_types.map((t) => t.id));
  const old = draft.tile_assignment;
  const { nx, ny } = draft.grid;

  const next: string[] = [];
  for (let y = 0; y < ny; y += 1) {
    for (let x = 0; x < nx; x += 1) {
      const existed = x < previous.nx && y < previous.ny;
      const carried = existed ? old[assignmentIndex(previous.nx, x, y)] : undefined;
      next.push(carried && known.has(carried) ? carried : fallback);
    }
  }
  draft.tile_assignment = next;
}
