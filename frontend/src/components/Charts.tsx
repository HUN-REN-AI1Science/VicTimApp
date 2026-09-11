/**
 * Small dependency-free SVG charts.
 *
 * These reproduce the standard FORMIND/GRASSMIND output plots -- biomass through
 * time by functional type, stem number by diameter class -- rather than offering
 * a general charting toolkit, which is why they are 150 lines instead of a
 * library dependency.
 */

import type { HistogramBin } from "../types";

export interface Series {
  label: string;
  colour: string;
  values: number[];
  dashed?: boolean;
}

const PAD = { top: 8, right: 8, bottom: 20, left: 42 };

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const scaled = value / magnitude;
  const step = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
  return step * magnitude;
}

/**
 * Vertical domain for a line chart.
 *
 * A series that never goes negative keeps the zero floor it has always had.
 * Once any value is negative the floor has to drop with it, or the negative
 * part of the trajectory is drawn below the plot and silently disappears --
 * which is how a stand running a carbon debt for centuries read as a flatline
 * at zero.
 *
 * The two sides are rounded outwards independently rather than forced
 * symmetric, so a shallow dip below zero under a large positive series stays
 * visibly shallow instead of being given half the plot height.
 */
function yDomain(values: number[]): { min: number; max: number } {
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  if (min >= 0) return { min: 0, max: niceMax(max) };
  return { min: -niceMax(-min), max: max > 0 ? niceMax(max) : 0 };
}

function format(value: number): string {
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1000) return value.toExponential(0);
  if (abs >= 10) return value.toFixed(0);
  if (abs >= 1) return value.toFixed(1);
  if (abs >= 0.01) return value.toFixed(2);
  return value.toExponential(0);
}

export function LineChart({
  x,
  series,
  height = 150,
  yLabel,
  marker,
}: {
  x: number[];
  series: Series[];
  height?: number;
  yLabel?: string;
  marker?: number;
}) {
  const width = 420;
  const inner = {
    w: width - PAD.left - PAD.right,
    h: height - PAD.top - PAD.bottom,
  };
  const allValues = series.flatMap((s) => s.values).filter(Number.isFinite);
  const { min: yMin, max: yMax } = yDomain(allValues);
  const ySpan = yMax - yMin;
  const xMax = Math.max(...x, 1);

  const px = (v: number) => PAD.left + (v / xMax) * inner.w;
  const py = (v: number) => PAD.top + inner.h - ((v - yMin) / ySpan) * inner.h;

  // With a floor below zero the midpoint tick is worth less than the bounds
  // and the zero line, so label those instead. Set-deduplicated because a
  // wholly negative series has 0 as its upper bound.
  const ticks = [...new Set(yMin < 0 ? [yMin, 0, yMax] : [0, 0.5 * yMax, yMax])];

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img">
        {ticks.map((t) => (
          <g key={t}>
            <line
              className={t === 0 && yMin < 0 ? "axis zero" : "axis"}
              x1={PAD.left}
              x2={width - PAD.right}
              y1={py(t)}
              y2={py(t)}
            />
            <text x={PAD.left - 5} y={py(t) + 3} textAnchor="end">
              {format(t)}
            </text>
          </g>
        ))}
        {[0, 0.5, 1].map((f) => (
          <text key={f} x={px(f * xMax)} y={height - 6} textAnchor="middle">
            {Math.round(f * xMax)}
          </text>
        ))}
        {marker !== undefined && (
          <line
            x1={px(marker)}
            x2={px(marker)}
            y1={PAD.top}
            y2={PAD.top + inner.h}
            stroke="var(--accent)"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        )}
        {series.map((s) => (
          <polyline
            key={s.label}
            fill="none"
            stroke={s.colour}
            strokeWidth={1.6}
            strokeDasharray={s.dashed ? "4 3" : undefined}
            points={s.values
              .map((v, i) => `${px(x[i] ?? i)},${py(Number.isFinite(v) ? v : 0)}`)
              .join(" ")}
          />
        ))}
        {yLabel && (
          <text x={PAD.left} y={PAD.top - 1} textAnchor="start">
            {yLabel}
          </text>
        )}
      </svg>
      <div className="legend">
        {series.map((s) => (
          <span key={s.label}>
            <i className="swatch" style={{ background: s.colour }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Stem number by diameter class -- the classic FORMIND stand-structure output. */
export function Histogram({ bins, height = 150 }: { bins: HistogramBin[]; height?: number }) {
  const width = 420;
  const inner = { w: width - PAD.left - PAD.right, h: height - PAD.top - PAD.bottom };
  const yMax = niceMax(Math.max(...bins.map((b) => b.stems), 0));
  const barWidth = inner.w / Math.max(bins.length, 1);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img">
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line
            className="axis"
            x1={PAD.left}
            x2={width - PAD.right}
            y1={PAD.top + inner.h * (1 - f)}
            y2={PAD.top + inner.h * (1 - f)}
          />
          <text x={PAD.left - 5} y={PAD.top + inner.h * (1 - f) + 3} textAnchor="end">
            {format(f * yMax)}
          </text>
        </g>
      ))}
      {bins.map((bin, i) => {
        const h = yMax > 0 ? (bin.stems / yMax) * inner.h : 0;
        return (
          <rect
            key={i}
            x={PAD.left + i * barWidth + 1}
            y={PAD.top + inner.h - h}
            width={Math.max(barWidth - 2, 1)}
            height={h}
            fill="var(--accent)"
            opacity={0.85}
          />
        );
      })}
      {bins.map((bin, i) =>
        i % 2 === 0 ? (
          <text
            key={`t${i}`}
            x={PAD.left + i * barWidth + barWidth / 2}
            y={height - 6}
            textAnchor="middle"
          >
            {Math.round(bin.lower * 100)}
          </text>
        ) : null,
      )}
    </svg>
  );
}
