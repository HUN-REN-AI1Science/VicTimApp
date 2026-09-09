/**
 * The region drawn by land use, with a legend.
 *
 * The companion to `TileMap`, which colours tiles by a simulated variable. This
 * one colours them by the thing the user chose, so the region is a picture from
 * the moment it is configured rather than from the moment a run finishes — the
 * map is how you edit the region, and an editor you cannot see until after the
 * job completes is not an editor.
 *
 * Categorical rather than a ramp, so it deliberately does not share `TileMap`'s
 * colour-scale machinery: there is no "high" or "low" land use to normalise.
 */

import type { ScenarioConfig } from "../types";
import { typeIdAt, typeById } from "../lib/tiles";

export function TileTypeMap({
  config,
  selected,
  onSelect,
}: {
  config: ScenarioConfig;
  selected: { x: number; y: number };
  onSelect: (tile: { x: number; y: number }) => void;
}) {
  const { nx, ny } = config.grid;
  const used = new Set(
    Array.from({ length: nx * ny }, (_, i) => typeIdAt(config, i % nx, Math.floor(i / nx))),
  );

  return (
    <>
      <div className="tilegrid" style={{ gridTemplateColumns: `repeat(${nx}, 1fr)` }}>
        {Array.from({ length: nx * ny }, (_, i) => {
          const x = i % nx;
          const y = Math.floor(i / nx);
          const type = typeById(config.tile_types, typeIdAt(config, x, y));
          const isSelected = selected.x === x && selected.y === y;
          return (
            <div
              key={i}
              className={`tile${isSelected ? " selected" : ""}`}
              style={{ background: type?.colour ?? "#ccc" }}
              title={`(${x}, ${y}) — ${type?.label ?? "unassigned"}`}
              onClick={() => onSelect({ x, y })}
            />
          );
        })}
      </div>

      <div className="typelegend">
        {config.tile_types
          .filter((t) => used.has(t.id))
          .map((t) => (
            <span key={t.id}>
              <b style={{ background: t.colour }} />
              {t.label}
            </span>
          ))}
      </div>
    </>
  );
}
