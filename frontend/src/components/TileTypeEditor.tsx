/**
 * Everything that can differ between one tile and another, edited where the
 * tile is selected.
 *
 * This does not live in the sidebar, and that is the point. The sidebar holds
 * the region: one soil column's properties, one climate, one grid, one set of
 * PFTs. Those are true of every tile and are edited without reference to any
 * tile. Management and initial vegetation are *not* true of every tile, so they
 * are edited here, against the tile the map has selected — a form that changes
 * one tile is only legible next to the picture of which tile that is.
 *
 * Edits apply to the tile's **type**, not to the tile. That is what makes a
 * 16×16 region configurable: five land uses and an assignment rather than 256
 * forms. The panel says so where the edits happen, because it is the one thing
 * about this design that can surprise.
 */

import type { ManagementPreset, ManagementPresetId, ScenarioConfig, TileTypeConfig } from "../types";
import { assignmentIndex, typeIdAt } from "../lib/tiles";
import { CheckField, NumberField } from "./fields";

type Patch = (update: (draft: ScenarioConfig) => void) => void;

/** A new id that no existing type is using. */
function freeId(types: TileTypeConfig[], base: string): string {
  if (!types.some((t) => t.id === base)) return base;
  for (let n = 2; ; n += 1) {
    const candidate = `${base}-${n}`;
    if (!types.some((t) => t.id === candidate)) return candidate;
  }
}

export function TileTypeEditor({
  config,
  patch,
  presets,
  selected,
  onOpenTile,
}: {
  config: ScenarioConfig;
  patch: Patch;
  presets: ManagementPreset[];
  selected: { x: number; y: number };
  onOpenTile: () => void;
}) {
  const { nx, ny } = config.grid;
  const currentId = typeIdAt(config, selected.x, selected.y);
  const type = config.tile_types.find((t) => t.id === currentId);
  if (!type) return null;

  // Counted off the grid rather than the assignment array, which is allowed to
  // be empty: an empty assignment means every tile takes the first type.
  const tilesOfThisType = Array.from({ length: nx * ny }).filter(
    (_, i) => typeIdAt(config, i % nx, Math.floor(i / nx)) === currentId,
  ).length;

  /** Assign `id` to every tile the predicate accepts. */
  const paint = (id: string, keep: (x: number, y: number) => boolean) =>
    patch((draft) => {
      for (let y = 0; y < ny; y += 1) {
        for (let x = 0; x < nx; x += 1) {
          if (keep(x, y)) draft.tile_assignment[assignmentIndex(nx, x, y)] = id;
        }
      }
    });

  /** Edit the selected type in place. */
  const editType = (update: (draft: TileTypeConfig) => void) =>
    patch((draft) => {
      const target = draft.tile_types.find((t) => t.id === currentId);
      if (target) update(target);
    });

  const applyPreset = (preset: ManagementPreset) =>
    editType((t) => {
      t.management = {
        preset: preset.id as ManagementPresetId,
        mowing: preset.mowing.map((m) => ({ ...m })),
        grazing: preset.grazing.map((g) => ({ ...g })),
        fertilisation: preset.fertilisation.map((f) => ({ ...f })),
      };
    });

  const addType = () =>
    patch((draft) => {
      const id = freeId(draft.tile_types, "custom");
      draft.tile_types.push({
        ...structuredClone(type),
        id,
        label: `${type.label} (copy)`,
      });
      draft.tile_assignment[assignmentIndex(nx, selected.x, selected.y)] = id;
    });

  const removeType = () =>
    patch((draft) => {
      if (draft.tile_types.length < 2) return;
      draft.tile_types = draft.tile_types.filter((t) => t.id !== currentId);
      const fallback = draft.tile_types[0].id;
      draft.tile_assignment = draft.tile_assignment.map((id) =>
        id === currentId ? fallback : id,
      );
    });

  return (
    <section className="card tile-editor">
      <h2>
        Tile ({selected.x}, {selected.y})
        <em>
          <button className="link" onClick={onOpenTile}>
            open its outputs →
          </button>
        </em>
      </h2>

      <div className="field">
        <label>land use</label>
        <select
          value={currentId}
          onChange={(e) => paint(e.target.value, (x, y) => x === selected.x && y === selected.y)}
        >
          {config.tile_types.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      </div>

      {nx * ny > 1 && (
        <>
          <div className="group-label">apply this land use to</div>
          <div className="paint-row">
            <button onClick={() => paint(currentId, (_x, y) => y === selected.y)}>row</button>
            <button onClick={() => paint(currentId, (x) => x === selected.x)}>column</button>
            <button onClick={() => paint(currentId, () => true)}>whole region</button>
          </div>
        </>
      )}

      <hr />

      <div className="group-label">
        {type.label} — {tilesOfThisType} tile{tilesOfThisType === 1 ? "" : "s"}
      </div>
      <p className="hint">
        These are the parameters of the <em>type</em>, so an edit here changes every tile using
        it. Duplicate the type first if you want this tile to differ from the others.
      </p>

      <div className="field">
        <label>name</label>
        <input
          type="text"
          value={type.label}
          onChange={(e) => editType((t) => void (t.label = e.target.value))}
        />
      </div>
      <div className="field">
        <label>map colour</label>
        <input
          type="color"
          value={type.colour}
          onChange={(e) => editType((t) => void (t.colour = e.target.value))}
        />
      </div>
      <div className="paint-row">
        <button onClick={addType}>duplicate type</button>
        <button onClick={removeType} disabled={config.tile_types.length < 2}>
          delete type
        </button>
      </div>

      <div className="group-label">management</div>
      <div className="preset-grid">
        {presets.map((preset) => (
          <button
            key={preset.id}
            className={`preset${type.management.preset === preset.id ? " active" : ""}`}
            onClick={() => applyPreset(preset)}
            title={preset.description}
          >
            <strong>{preset.label}</strong>
            <span>{preset.description}</span>
          </button>
        ))}
      </div>

      {type.management.mowing.length > 0 && (
        <>
          <div className="group-label">cuts (day of year / height m)</div>
          {type.management.mowing.map((event, i) => (
            <div className="event-row" key={i}>
              <input
                type="number"
                value={event.day_of_year}
                onChange={(e) =>
                  editType((t) => {
                    t.management.mowing[i].day_of_year = Number(e.target.value);
                    t.management.preset = "custom";
                  })
                }
              />
              <input
                type="number"
                step="0.01"
                value={event.cut_height_m}
                onChange={(e) =>
                  editType((t) => {
                    t.management.mowing[i].cut_height_m = Number(e.target.value);
                    t.management.preset = "custom";
                  })
                }
              />
              <button
                onClick={() =>
                  editType((t) => {
                    t.management.mowing.splice(i, 1);
                    t.management.preset = "custom";
                  })
                }
              >
                ×
              </button>
            </div>
          ))}
        </>
      )}
      <button
        onClick={() =>
          editType((t) => {
            t.management.mowing.push({
              day_of_year: 190,
              cut_height_m: 0.07,
              removal_fraction: 0.9,
              woody_kill_height_m: 0.6,
            });
            t.management.preset = "custom";
          })
        }
      >
        + add cut
      </button>
      <p className="hint">
        A cut also destroys tree saplings below its woody-kill height. That is what keeps a
        managed meadow from turning into woodland.
      </p>

      <div className="group-label">vegetation at year zero</div>
      <CheckField
        id={`grass-${currentId}`}
        label="grassland (GRASSMIND)"
        checked={type.vegetation.include_grassland}
        onChange={(v) => editType((t) => void (t.vegetation.include_grassland = v))}
      />
      <CheckField
        id={`forest-${currentId}`}
        label="forest (FORMIND)"
        checked={type.vegetation.include_forest}
        onChange={(v) => editType((t) => void (t.vegetation.include_forest = v))}
      />
      <NumberField
        label="initial sward density"
        unit="plants m-2"
        value={type.vegetation.initial_sward_density_per_m2}
        onChange={(v) => editType((t) => void (t.vegetation.initial_sward_density_per_m2 = v))}
      />
      <NumberField
        label="planted trees"
        unit="per tile"
        step="1"
        value={type.vegetation.initial_trees_per_tile}
        onChange={(v) =>
          editType((t) => void (t.vegetation.initial_trees_per_tile = Math.max(0, Math.round(v))))
        }
      />
      <NumberField
        label="planted tree size"
        unit="m dbh"
        step="0.01"
        value={type.vegetation.initial_tree_dbh}
        onChange={(v) => editType((t) => void (t.vegetation.initial_tree_dbh = v))}
      />
    </section>
  );
}
