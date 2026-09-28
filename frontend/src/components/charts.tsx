/* Zero-dependency SVG chart primitives, tuned for the terminal aesthetic. */

import { useId } from "react";

function scalePath(values: number[], w: number, h: number, pad = 2): string {
  if (values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = (w - pad * 2) / (values.length - 1);
  return values
    .map((v, i) => {
      const x = pad + i * step;
      const y = h - pad - ((v - min) / span) * (h - pad * 2);
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

/** Tiny inline sparkline — used for IC decay curves in tables. */
export function Sparkline({
  values,
  width = 96,
  height = 26,
  stroke = "#34d399",
}: {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
}) {
  const d = scalePath(values, width, height);
  const last = values[values.length - 1] ?? 0;
  return (
    <svg width={width} height={height} className="overflow-visible" aria-hidden>
      <path d={d} fill="none" stroke={stroke} strokeWidth="1.4" opacity="0.9" />
      {d && (
        <circle
          cx={width - 2}
          cy={height - 2 - ((last - Math.min(...values)) / (Math.max(...values) - Math.min(...values) || 1)) * (height - 4)}
          r="2"
          fill={stroke}
        />
      )}
    </svg>
  );
}

/** Area chart for the aggregate equity curve — flat fill, no glow. */
export function AreaChart({
  values,
  width = 640,
  height = 180,
  stroke = "#34d399",
}: {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
}) {
  const gid = useId();
  const d = scalePath(values, width, height, 4);
  if (!d) return <svg className="block w-full h-44" viewBox={`0 0 ${width} ${height}`} />;
  const area = `${d} L${width - 4},${height - 2} L4,${height - 2} Z`;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="block w-full h-44">
      <defs>
        <linearGradient id={`${gid}-fill`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.16" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0.01" />
        </linearGradient>
      </defs>
      {/* horizontal grid rules */}
      {[0.25, 0.5, 0.75].map((f) => (
        <line
          key={f}
          x1="4"
          x2={width - 4}
          y1={height * f}
          y2={height * f}
          stroke="#64748b"
          strokeOpacity="0.14"
        />
      ))}
      <path d={area} fill={`url(#${gid}-fill)`} />
      <path d={d} fill="none" stroke={stroke} strokeWidth="1.5" />
    </svg>
  );
}

/** Overlayed multi-series line chart (Compare / RunDetail drawdown). */
export function MultiLine({
  series,
  width = 640,
  height = 220,
}: {
  series: Array<{ label: string; values: number[]; color: string }>;
  width?: number;
  height?: number;
}) {
  const populated = series.filter((s) => s.values.length > 1);
  if (populated.length === 0) return <svg className="block w-full h-52" viewBox={`0 0 ${width} ${height}`} />;

  // shared y-scale so the overlay is honest
  const all = populated.flatMap((s) => s.values);
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const pad = 6;

  const path = (values: number[]) => {
    const step = (width - pad * 2) / (values.length - 1);
    return values
      .map((v, i) => {
        const x = pad + i * step;
        const y = height - pad - ((v - min) / span) * (height - pad * 2);
        return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");
  };

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="block w-full h-52">
      {[0.25, 0.5, 0.75].map((f) => (
        <line
          key={f}
          x1={pad}
          x2={width - pad}
          y1={height * f}
          y2={height * f}
          stroke="#64748b"
          strokeOpacity="0.14"
        />
      ))}
      {populated.map((s) => (
        <path key={s.label} d={path(s.values)} fill="none" stroke={s.color} strokeWidth="1.5" opacity="0.95" />
      ))}
    </svg>
  );
}

/** Horizontal meter bar (CPU / MEM / sentiment). */
export function Meter({
  pct,
  color = "#818cf8",
}: {
  pct: number; // 0..100
  color?: string;
}) {
  return (
    <div className="h-1 w-full rounded-full bg-slate-800 overflow-hidden">
      <div
        className="h-full rounded-full transition-[width] duration-700 ease-out"
        style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: color }}
      />
    </div>
  );
}
