/**
 * Small dependency-free SVG charts.
 *
 * These reproduce the standard FORMIND/GRASSMIND output plots -- biomass through
 * time by functional type, stem number by diameter class -- rather than offering
 * a general charting toolkit, which is why they are ~200 lines instead of a
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
 * Y-axis domain and tick values for a set of samples.
 *
 * The domain always contains zero so the sign of every value can be read off the
 * chart. When nothing is negative the floor is zero, as before; when something
 * is, the floor extends to a nice round value below the most negative sample, so
 * a series that turns negative is drawn instead of being clipped at the floor.
 */
export function yDomain(values: number[]): { min: number; max: number; ticks: number[] } {
  const finite = values.filter(Number.isFinite);
  const lo = Math.min(...finite, 0);
  const hi = Math.max(...finite, 0);
  if (lo >= 0) {
    const max = niceMax(hi);
    return { min: 0, max, ticks: [0, max / 2, max] };
  }
  const min = -niceMax(-lo);
  if (hi <= 0) return { min, max: 0, ticks: [min, min / 2, 0] };
  const max = niceMax(hi);
  return { min, max, ticks: [min, 0, max] };
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
  const y = yDomain(series.flatMap((s) => s.values));
  const xMax = Math.max(...x, 1);

  const px = (v: number) => PAD.left + (v / xMax) * inner.w;
  const py = (v: number) => PAD.top + inner.h - ((v - y.min) / (y.max - y.min)) * inner.h;

  // When one side of zero is much shorter than the other, its end tick sits
  // almost on the zero tick; keep the gridline but drop the colliding label.
  const MIN_LABEL_GAP_PX = 10;
  const showLabel = (t: number) => t === 0 || Math.abs(py(t) - py(0)) >= MIN_LABEL_GAP_PX;

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img">
        {y.ticks.map((t) => (
          <g key={t}>
            <line className="axis" x1={PAD.left} x2={width - PAD.right} y1={py(t)} y2={py(t)} />
            {showLabel(t) && (
              <text x={PAD.left - 5} y={py(t) + 3} textAnchor="end">
                {format(t)}
              </text>
            )}
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
        {y.min < 0 && (
          <line
            className="axis zero"
            x1={PAD.left}
            x2={width - PAD.right}
            y1={py(0)}
            y2={py(0)}
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
