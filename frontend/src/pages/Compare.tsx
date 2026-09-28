/* Compare — overlay any two backtest runs on a shared axis and
 * diff their metrics side by side. */

import { useEffect, useMemo, useState } from "react";
import { api, type RunDetailData, type RunSummary } from "../lib/api";
import { MultiLine } from "../components/charts";
import { PanelHeader } from "../components/Terminal";

const COLOR_A = "#34d399";
const COLOR_B = "#818cf8";

function RunSelect({
  label,
  color,
  runs,
  value,
  onChange,
}: {
  label: string;
  color: string;
  runs: RunSummary[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-[11px] text-slate-400">
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-[#0a0e14] border border-slate-700/60 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 outline-none focus:border-indigo-400/50"
      >
        {runs.map((r) => (
          <option key={r.id} value={r.id}>
            {r.factorName} · {r.engine} ({r.id})
          </option>
        ))}
      </select>
    </label>
  );
}

function DiffRow({ label, a, b, higherBetter = true, unit = "" }: { label: string; a: number; b: number; higherBetter?: boolean; unit?: string }) {
  const winA = higherBetter ? a >= b : a <= b;
  return (
    <tr className="border-b border-slate-800/50">
      <td className="px-4 py-2 text-slate-500 uppercase tracking-[0.08em] text-[9px]">{label}</td>
      <td className={`px-4 py-2 text-right tabular-nums font-mono font-semibold ${winA ? "text-emerald-400" : "text-slate-400"}`}>
        {a.toFixed(2)}{unit}
      </td>
      <td className={`px-4 py-2 text-right tabular-nums font-mono font-semibold ${!winA ? "text-indigo-300" : "text-slate-400"}`}>
        {b.toFixed(2)}{unit}
      </td>
    </tr>
  );
}

export default function Compare() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [aId, setAId] = useState("");
  const [bId, setBId] = useState("");
  const [a, setA] = useState<RunDetailData | null>(null);
  const [b, setB] = useState<RunDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .runs()
      .then((rs) => {
        setRuns(rs);
        if (rs.length >= 2) {
          setAId(rs[0].id);
          setBId(rs[1].id);
        }
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (aId) api.run(aId).then(setA).catch(() => setA(null));
  }, [aId]);
  useEffect(() => {
    if (bId) api.run(bId).then(setB).catch(() => setB(null));
  }, [bId]);

  // both re-based to 1.0 and clipped to the shorter run for an honest overlay
  const series = useMemo(() => {
    if (!a || !b) return [];
    const n = Math.min(a.nav.length, b.nav.length);
    const rebase = (nav: Array<{ nav: number }>) => {
      const tail = nav.slice(-n);
      const base = tail[0].nav;
      return tail.map((x) => x.nav / base);
    };
    return [
      { label: a.id, values: rebase(a.nav), color: COLOR_A },
      { label: b.id, values: rebase(b.nav), color: COLOR_B },
    ];
  }, [a, b]);

  return (
    <div className="flex flex-col gap-4">
      <section className="aq-glass rounded-lg p-4 flex flex-wrap items-center gap-4">
        <div className="mr-auto">
          <h1 className="text-sm font-semibold text-slate-100 tracking-tight">
            Engine Compare
          </h1>
          <p className="text-[10px] text-slate-500 mt-0.5">overlayed NAV, rebased to 1.0 over the common window</p>
        </div>
        <RunSelect label="A" color={COLOR_A} runs={runs} value={aId} onChange={setAId} />
        <RunSelect label="B" color={COLOR_B} runs={runs} value={bId} onChange={setBId} />
      </section>

      {error && (
        <section className="aq-glass rounded-lg p-8 text-center text-rose-400 text-[11px]">
          backend unreachable — start the API to compare runs
        </section>
      )}

      {a && b && (
        <>
          <section className="aq-glass rounded-lg overflow-hidden">
            <PanelHeader
              title="NAV Overlay"
              right={
                <span className="text-[10px] text-slate-500">
                  <span style={{ color: COLOR_A }}>{a.factorName}</span> vs{" "}
                  <span style={{ color: COLOR_B }}>{b.factorName}</span>
                </span>
              }
            />
            <div className="p-3 pt-4">
              <MultiLine series={series} />
            </div>
          </section>

          <section className="aq-glass rounded-lg overflow-hidden max-w-xl">
            <PanelHeader title="Metric Diff" />
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-[9px] uppercase tracking-[0.08em] text-slate-500 border-b border-slate-700/40">
                  <th className="px-4 py-2 text-left font-semibold">Metric</th>
                  <th className="px-4 py-2 text-right font-semibold" style={{ color: COLOR_A }}>
                    {a.id}
                  </th>
                  <th className="px-4 py-2 text-right font-semibold" style={{ color: COLOR_B }}>
                    {b.id}
                  </th>
                </tr>
              </thead>
              <tbody>
                <DiffRow label="Sharpe" a={a.metrics.sharpe} b={b.metrics.sharpe} />
                <DiffRow label="Ann. Return" a={a.metrics.annRetPct} b={b.metrics.annRetPct} unit="%" />
                <DiffRow label="Max Drawdown" a={a.metrics.maxDrawdownPct} b={b.metrics.maxDrawdownPct} higherBetter={false} unit="%" />
                <DiffRow label="Hit Rate" a={a.metrics.winRatePct} b={b.metrics.winRatePct} unit="%" />
                <DiffRow label="Final NAV" a={a.metrics.finalNav} b={b.metrics.finalNav} />
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}
