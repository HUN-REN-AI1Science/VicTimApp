/**
 * The region: the map, and everything about the region you edit through it.
 *
 * One tab rather than two, and present before a run rather than after it. The
 * map is the tile selector, so it belongs beside the tile it selects; and it is
 * also how a region is drawn, so it has to exist while the region is still being
 * described. It used to appear only once a job finished, which made every
 * scenario look like a single tile right up to the moment it completed.
 *
 * Colouring is by land use until there is output, and by any recorded variable
 * afterwards. The land-use view never goes away: it is the only one in which the
 * region is editable.
 */

import { MAP_VARIABLES, TileMap, type MapVariable } from "./TileMap";
import { TileTypeMap } from "./TileTypeMap";
import { TileTypeEditor } from "./TileTypeEditor";
import type { ManagementPreset, ScenarioConfig, TileSeries } from "../types";

export const TYPE_VIEW = "tile_type";

export function RegionPanel({
  config,
  patch,
  presets,
  tiles,
  index,
  variable,
  onVariableChange,
  selected,
  onSelect,
  onOpenTile,
}: {
  config: ScenarioConfig;
  patch: (update: (draft: ScenarioConfig) => void) => void;
  presets: ManagementPreset[];
  /** Results, if a run has finished. Absent while the region is only configured. */
  tiles?: TileSeries[];
  index: number;
  variable: MapVariable | null;
  onVariableChange: (variable: MapVariable | null) => void;
  selected: { x: number; y: number };
  onSelect: (tile: { x: number; y: number }) => void;
  onOpenTile: () => void;
}) {
  const { nx, ny, tile_size_m } = config.grid;
  const hectares = (nx * ny * tile_size_m ** 2) / 10000;
  const independent = config.grid.dispersal === "none" && config.grid.lateral_shading === "none";
  // Output colouring needs output. Before a run there is exactly one view.
  const showOutput = Boolean(tiles) && variable !== null;

  return (
    <div className="region">
      <section className="card">
        <h2>
          Region
          <em>
            {nx} × {ny} tiles · {tile_size_m} m each · {hectares.toFixed(2)} ha
          </em>
        </h2>

        <div className="field">
          <label>colour by</label>
          <select
            value={showOutput ? variable!.key : TYPE_VIEW}
            onChange={(event) =>
              onVariableChange(
                event.target.value === TYPE_VIEW
                  ? null
                  : (MAP_VARIABLES.find((v) => v.key === event.target.value) ?? null),
              )
            }
          >
            <option value={TYPE_VIEW}>land use</option>
            {tiles &&
              MAP_VARIABLES.map((v) => (
                <option key={v.key} value={v.key}>
                  {v.label}
                </option>
              ))}
          </select>
        </div>

        {showOutput ? (
          <TileMap
            tiles={tiles!}
            nx={nx}
            ny={ny}
            index={index}
            variable={variable!}
            selected={selected}
            onSelect={onSelect}
          />
        ) : (
          <TileTypeMap config={config} selected={selected} onSelect={onSelect} />
        )}

        <p className="hint">
          {independent
            ? "Seed dispersal and lateral shading are both off, so these tiles are independent columns — the same site simulated n times."
            : "Seeds and sky cross tile boundaries in this run, so a tile’s neighbours are part of its result."}
          {!tiles && " Press Run to fill the map with output."}
        </p>
      </section>

      <TileTypeEditor
        config={config}
        patch={patch}
        presets={presets}
        selected={selected}
        onOpenTile={onOpenTile}
      />
    </div>
  );
}
