/**
 * The vertical stand-structure view.
 *
 * This is the picture that makes the coupling legible: tree crowns and the grass
 * sward beneath them drawn in ONE diagram, against one height axis, because in
 * the model they occupy one shared light profile. It mirrors the crown diagrams
 * FORMIND produces, with GRASSMIND's sward added at the bottom.
 *
 * FORMIND is horizontally position-free within a patch, so the model has no x
 * coordinate to give us. Positions here are generated deterministically from the
 * cohort index, which keeps the picture stable as the user scrubs through time
 * while being honest that horizontal placement is illustrative, not simulated.
 */

import type { StandRow, SwardRow } from "../types";

const MAX_DRAWN = 140;

/**
 * Fallback height of the profile's vertical axis (m), used before a run has
 * produced any structure to measure.
 *
 * The axis is fitted ONCE PER RUN -- to the tallest individual anywhere in the
 * run, plus a metre of headroom -- and never per step. A per-step axis rescales
 * as the user scrubs through time, which makes a stand that is actually growing
 * look static: the tallest tree is drawn at the top of the frame in year 5 and
 * in year 90 alike. See `heightAxisM` in `App`.
 */
export const DEFAULT_HEIGHT_AXIS_M = 20;

/**
 * Height below which the axis is magnified (m).
 *
 * The sward is a few tens of centimetres and the canopy is tens of metres, so
 * one linear axis cannot show both: at 20 m full-scale a 0.4 m sward is two
 * pixels. Below this height the axis runs at `BREAK_MAGNIFICATION` times the
 * scale used above it, which is the same trick a stand profile in the FORMIND
 * literature uses when it needs the regeneration layer and the overstorey in one
 * frame. The scale is piecewise LINEAR, not logarithmic, so a reader can still
 * measure off it -- but the break is marked, because an unmarked broken axis
 * misleads.
 */
const BREAK_M = 1;

/** How much larger the sub-`BREAK_M` scale is than the scale above it. */
const BREAK_MAGNIFICATION = 5;

/** Gridline spacing below the break (m). */
const FINE_TICK_M = 0.1;

/** Deterministic pseudo-random in [0, 1): stable across renders, no state. */
function jitter(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

interface Drawn {
  x: number;
  height: number;
  crownBase: number;
  crownWidth: number;
  colour: string;
  depth: number;
}

export function StandProfile({
  stand,
  sward,
  tileSizeM,
  floorLightFraction,
  heightAxisM = DEFAULT_HEIGHT_AXIS_M,
}: {
  stand: StandRow[];
  sward: SwardRow[];
  tileSizeM: number;
  floorLightFraction: number;
  /** Top of the height axis (m). Constant for a whole run -- see the constant. */
  heightAxisM?: number;
}) {
  const width = 640;
  const height = 300;
  const margin = { left: 34, right: 8, top: 10, bottom: 22 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  const yMax = heightAxisM;

  // Pixels per metre ABOVE the break. The plot is divided so that the lower
  // BREAK_M metres take BREAK_MAGNIFICATION times the room per metre that the
  // rest does: plotH = (yMax - BREAK_M) * upper + BREAK_M * BREAK_MAGNIFICATION
  // * upper.
  const upperPxPerM = plotH / (yMax - BREAK_M + BREAK_M * BREAK_MAGNIFICATION);
  const breakPx = BREAK_M * BREAK_MAGNIFICATION * upperPxPerM;

  /** Height (m) to y pixel, on the broken axis. */
  const py = (m: number) => {
    const above = margin.top + plotH;
    if (m <= BREAK_M) return above - m * BREAK_MAGNIFICATION * upperPxPerM;
    return above - breakPx - (m - BREAK_M) * upperPxPerM;
  };
  const px = (m: number) => margin.left + (m / tileSizeM) * plotW;
  const scale = plotW / tileSizeM;

  // Sample individuals proportionally to cohort abundance, capped so a stand of
  // ten thousand seedlings still renders in one frame.
  const totalStems = stand.reduce((sum, row) => sum + row.n, 0);
  const drawn: Drawn[] = [];
  let seed = 1;
  stand.forEach((row, cohortIndex) => {
    const share = totalStems > 0 ? row.n / totalStems : 0;
    const count = Math.max(row.n > 0 ? 1 : 0, Math.round(share * MAX_DRAWN));
    for (let i = 0; i < count; i += 1) {
      seed += 1;
      drawn.push({
        x: jitter(seed + cohortIndex * 37) * tileSizeM,
        height: row.height,
        crownBase: row.crown_base,
        crownWidth: row.crown_diameter,
        colour: row.colour,
        depth: jitter(seed * 1.7) * 0.35 + 0.65,
      });
    }
  });
  // Short trees first, so the overstorey is drawn over the understorey.
  drawn.sort((a, b) => a.height - b.height);

  // Labelled ticks: a coarse set above the break, a sparse set below it. Every
  // FINE_TICK_M gets a gridline below the break but only every 0.5 m a label --
  // ten labels in the magnified band would collide.
  const coarseStep = Math.max(5, Math.round((yMax - BREAK_M) / 4 / 5) * 5);
  const labelled: number[] = [0, 0.5, BREAK_M];
  for (let m = coarseStep; m <= yMax + 1e-9; m += coarseStep) labelled.push(m);

  const fineGrid: number[] = [];
  for (let m = FINE_TICK_M; m < BREAK_M - 1e-9; m += FINE_TICK_M) {
    fineGrid.push(Number(m.toFixed(2)));
  }

  const bandHeight = (m: number) => Math.max(py(0) - py(m), m > 0 ? 1 : 0);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="Stand structure">
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#eef4f8" />
          <stop offset="100%" stopColor="#dfe9ef" />
        </linearGradient>
        {/* Crowns are ellipses centred on a stem, so a tree near either edge of
            the tile spills past the plot -- over the axis labels on the left,
            which is what hid every tick between 1 m and the canopy top. Clip the
            vegetation to the plot; the axis gutter belongs to the axis. */}
        <clipPath id="plot-clip">
          <rect x={margin.left} y={margin.top} width={plotW} height={plotH} />
        </clipPath>
      </defs>

      <rect
        x={margin.left}
        y={margin.top}
        width={plotW}
        height={plotH}
        fill="url(#sky)"
        rx={3}
      />

      {/* Unlabelled 0.1 m gridlines inside the magnified band, so the sward can
          be read off the axis rather than merely seen. */}
      {fineGrid.map((t) => (
        <line
          key={`fine-${t}`}
          className="axis"
          x1={margin.left}
          x2={width - margin.right}
          y1={py(t)}
          y2={py(t)}
          opacity={0.35}
        />
      ))}

      {labelled.map((t) => (
        <g key={t}>
          {t > 0 && (
            <line className="axis" x1={margin.left} x2={width - margin.right} y1={py(t)} y2={py(t)} />
          )}
          <text x={margin.left - 5} y={py(t) + 3} textAnchor="end">
            {t < 10 ? t.toFixed(1) : t.toFixed(0)}
          </text>
        </g>
      ))}

      {/* The break itself: below this line the axis runs at BREAK_MAGNIFICATION
          times the scale above it. Dashed, and the only dashed rule in the
          figure, so the change of scale is visible without a caption over the
          stand. The tick labels either side carry the actual numbers. */}
      <line
        className="axis break"
        x1={margin.left}
        x2={width - margin.right}
        y1={py(BREAK_M)}
        y2={py(BREAK_M)}
        strokeDasharray="3 3"
      />


      {/* Trees: a stem plus an elliptical crown, exactly the geometry the light
          module integrates over. */}
      <g clipPath="url(#plot-clip)">
      {drawn.map((tree, i) => {
        const crownH = Math.max(py(tree.crownBase) - py(tree.height), 2);
        const crownW = Math.max(tree.crownWidth * scale, 2);
        return (
          <g key={i} opacity={tree.depth}>
            <line
              x1={px(tree.x)}
              x2={px(tree.x)}
              y1={py(0)}
              y2={py(tree.crownBase)}
              stroke="#5d4a35"
              strokeWidth={Math.max(0.6, tree.height * 0.035)}
            />
            <ellipse
              cx={px(tree.x)}
              cy={py(tree.crownBase) - crownH / 2}
              rx={crownW / 2}
              ry={crownH / 2}
              fill={tree.colour}
              opacity={0.75}
            />
          </g>
        );
      })}

      </g>

      {/* Sward: one band per functional group, stacked by height so the tallest
          group is visible behind the shorter ones. */}
      {[...sward]
        .sort((a, b) => b.height - a.height)
        .map((group) => (
          <rect
            key={group.pft}
            x={margin.left}
            y={py(group.height)}
            width={plotW}
            height={bandHeight(group.height)}
            fill={group.colour}
            opacity={0.5}
          />
        ))}

      <rect x={margin.left} y={py(0)} width={plotW} height={margin.bottom - 6} fill="var(--soil)" />

      {/* Ground line, drawn last. The 0 m gridline is laid down with the rest of
          the axis, before the crowns, the sward bands and the soil, so all three
          paint over it -- and the sward band sits exactly on it. Redrawing it on
          top is what makes the baseline the trees stand on visible. */}
      <line
        className="axis baseline"
        x1={margin.left}
        x2={width - margin.right}
        y1={py(0)}
        y2={py(0)}
      />

      <text x={margin.left + 4} y={margin.top + 12} style={{ fill: "var(--muted)" }}>
        height (m)
      </text>
      <text x={width - margin.right - 4} y={py(0) + 13} textAnchor="end" style={{ fill: "#fff" }}>
        {(floorLightFraction * 100).toFixed(1)}% of light reaches the floor
      </text>
    </svg>
  );
}
