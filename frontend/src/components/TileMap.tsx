/**
 * The tiled region, coloured by a chosen variable against a fixed colour scale.
 *
 * Renders an nx x ny grid; milestone 1 runs 1x1, so this is usually a single
 * square. It is written for the general case because the grid abstraction is,
 * and because selecting a tile is how the user picks which tile the stand
 * profile and charts describe.
 *
 * The colour scale is normalised over EVERY tile and EVERY recorded step of the
 * run, not over the tiles present in the current step. Normalising per step is
 * what a spatial map usually wants, but it makes the single-tile case
 * meaningless -- the one tile is always its own maximum, so the square sits at
 * the dark end of the ramp for the whole run and shows nothing. A run-wide
 * domain means the colour is comparable across time as the user scrubs, which is
 * the only reading that works at both 1x1 and nx x ny.
 */

import { useMemo } from "react";

import type { TileSeries } from "../types";

export interface MapVariable {
  key: string;
  label: string;
  unit: string;
  /** Low-to-high colour ramp. */
  ramp: [string, string];
}

export const MAP_VARIABLES: MapVariable[] = [
  { key: "forest_biomass_c", label: "Tree biomass", unit: "kgC m⁻²", ramp: ["#eef2ea", "#1f4f36"] },
  { key: "grassland_shoot_c", label: "Sward biomass", unit: "kgC m⁻²", ramp: ["#f7f6ec", "#8a9e3b"] },
  { key: "lai", label: "Leaf area index", unit: "m² m⁻²", ramp: ["#f4f6f2", "#2f6f4e"] },
  { key: "soil_c", label: "Soil carbon", unit: "kgC m⁻²", ramp: ["#f6f1ea", "#4a3a26"] },
  { key: "mineral_n", label: "Mineral nitrogen", unit: "kgN m⁻²", ramp: ["#f4f1f6", "#5b3f74"] },
];

const LEGEND_STOPS = 5;

function mix(a: string, b: string, t: number): string {
  const parse = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const [r1, g1, b1] = parse(a);
  const [r2, g2, b2] = parse(b);
  const c = (x: number, y: number) => Math.round(x + (y - x) * Math.min(1, Math.max(0, t)));
  return `rgb(${c(r1, r2)},${c(g1, g2)},${c(b1, b2)})`;
}

/** Significant-figure formatting, so a 1e-5 nitrogen pool is not printed "0.00". */
function fmt(v: number): string {
  if (v === 0) return "0";
  const abs = Math.abs(v);
  if (abs >= 100) return v.toFixed(0);
  if (abs >= 1) return v.toFixed(2);
  if (abs >= 0.001) return v.toFixed(3);
  return v.toExponential(1);
}

export function TileMap({
  tiles,
  nx,
  ny,
  index,
  variable,
  selected,
  onSelect,
}: {
  tiles: TileSeries[];
  nx: number;
  ny: number;
  index: number;
  variable: MapVariable;
  selected: { x: number; y: number };
  onSelect: (tile: { x: number; y: number }) => void;
}) {
  // Run-wide domain: every tile, every step. Recomputed only when the results or
  // the chosen variable change, never as the user scrubs through time.
  const domainMax = useMemo(() => {
    let max = 0;
    for (const t of tiles) {
      for (const record of t.series) {
        const v = record?.[variable.key];
        if (typeof v === "number" && Number.isFinite(v) && v > max) max = v;
      }
    }
    return max;
  }, [tiles, variable.key]);

  // An all-zero variable (no trees yet, say) has no scale to draw against; keep
  // the ramp at its low end rather than dividing by zero.
  const scaleMax = domainMax > 0 ? domainMax : 1;
  const colourFor = (value: number) => mix(variable.ramp[0], variable.ramp[1], value / scaleMax);

  const selectedValue =
    tiles.find((t) => t.x === selected.x && t.y === selected.y)?.series[index]?.[variable.key] ?? 0;

  return (
    <>
      <div className="tilegrid" style={{ gridTemplateColumns: `repeat(${nx}, 1fr)` }}>
        {Array.from({ length: nx * ny }, (_, i) => {
          const x = i % nx;
          const y = Math.floor(i / nx);
          const tile = tiles.find((t) => t.x === x && t.y === y);
          const value = tile?.series[index]?.[variable.key] ?? 0;
          const isSelected = selected.x === x && selected.y === y;
          return (
            <div
              key={i}
              className={`tile${isSelected ? " selected" : ""}`}
              style={{ background: colourFor(value) }}
              title={`(${x}, ${y}) — ${variable.label} ${fmt(value)} ${variable.unit}`}
              onClick={() => onSelect({ x, y })}
            />
          );
        })}
      </div>

      <div className="colourscale">
        <div className="colourscale-bar">
          {Array.from({ length: LEGEND_STOPS * 8 }, (_, i) => (
            <span
              key={i}
              style={{ background: colourFor((i / (LEGEND_STOPS * 8 - 1)) * scaleMax) }}
            />
          ))}
          {/* Where this tile sits on the scale, this step. */}
          <b
            className="colourscale-marker"
            style={{ left: `${Math.min(100, Math.max(0, (selectedValue / scaleMax) * 100))}%` }}
          />
        </div>
        <div className="colourscale-ticks">
          {Array.from({ length: LEGEND_STOPS }, (_, i) => (
            <span key={i}>{fmt((i / (LEGEND_STOPS - 1)) * scaleMax)}</span>
          ))}
        </div>
      </div>

      <p className="hint">
        {variable.label} ({variable.unit}) · scale fixed over the whole run
        {domainMax > 0 ? "" : " · no values yet"}
        {nx * ny > 1 ? " · click a tile to inspect it" : ""}
      </p>
    </>
  );
}
