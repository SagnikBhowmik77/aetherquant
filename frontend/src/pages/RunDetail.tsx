/* RunDetail — per-run drilldown: NAV + drawdown charts, metrics,
 * and the execution trace, all fetched live from the API. */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type RunDetailData, type RunSummary } from "../lib/api";
import { AreaChart, MultiLine } from "../components/charts";
import { PanelHeader, fmtClock } from "../components/Terminal";

function Metric({ label, value, accent = "text-slate-100" }: { label: string; value: string; accent?: string }) {
  return (
    <div className="aq-glass rounded-lg px-4 py-3">
      <p className="text-[9px] font-medium uppercase tracking-[0.08em] text-slate-500">{label}</p>
      <p className={`text-lg font-semibold font-mono tabular-nums ${accent}`}>{value}</p>
    </div>
  );
}

export default function RunDetail() {
  const [params, setParams] = useSearchParams();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [detail, setDetail] = useState<RunDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selected = params.get("run");

  const refresh = useCallback(async () => {
    try {
      const rs = await api.runs();
      setRuns(rs);
      setError(null);
      return rs;
    } catch (e) {
      setError(`backend unreachable — ${String(e)}`);
      return [];
    }
  }, []);

  useEffect(() => {
    void refresh().then((rs) => {
      if (!selected && rs.length > 0) setParams({ run: rs[0].id }, { replace: true });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selected) return;
    api.run(selected).then(setDetail).catch((e) => setError(String(e)));
  }, [selected]);

  const drawdown = useMemo(() => {
    if (!detail) return [];
    let peak = 0;
    return detail.nav.map((m) => {
      peak = Math.max(peak, m.nav);
      return (m.nav / peak - 1) * 100;
    });
  }, [detail]);

  const m = detail?.metrics;
  const positive = (detail?.metrics.finalNav ?? 1) >= 1;

  return (
    <div className="flex flex-col xl:flex-row gap-4 items-start">
      {/* ── run list ── */}
      <section className="aq-glass rounded-lg overflow-hidden w-full xl:w-72 shrink-0">
        <PanelHeader
          title={`Runs · ${runs.length}`}
          right={
            <button onClick={() => void refresh()} className="text-[10px] text-indigo-300 hover:text-indigo-200">
              ↻ refresh
            </button>
          }
        />
        <div className="divide-y divide-slate-800/60 max-h-[560px] overflow-y-auto aq-scroll">
          {error && <p className="px-4 py-3 text-[10px] text-rose-400">{error}</p>}
          {runs.map((r) => (
            <button
              key={r.id}
              onClick={() => setParams({ run: r.id })}
              className={`w-full text-left px-4 py-2.5 text-[11px] transition-colors ${
                r.id === selected ? "bg-indigo-500/10 border-l-2 border-indigo-400" : "hover:bg-slate-800/40"
              }`}
            >
              <div className="flex justify-between gap-2">
                <span className="text-slate-200 font-semibold truncate">{r.factorName}</span>
                <span
                  className={`tabular-nums font-mono font-semibold shrink-0 ${
                    r.metrics.sharpe >= 0 ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {r.metrics.sharpe.toFixed(2)}
                </span>
              </div>
              <p className="text-[9px] text-slate-500 font-mono mt-0.5">
                {r.id} · {r.engine} · {r.days}d · {r.elapsedMs}ms
              </p>
            </button>
          ))}
        </div>
      </section>

      {/* ── detail ── */}
      <div className="flex-1 w-full flex flex-col gap-4 min-w-0">
        {detail && m ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <Metric label="Sharpe" value={m.sharpe.toFixed(2)} accent={m.sharpe >= 0 ? "text-emerald-400" : "text-rose-400"} />
              <Metric label="Ann. Return" value={`${m.annRetPct >= 0 ? "+" : ""}${m.annRetPct.toFixed(1)}%`} accent={m.annRetPct >= 0 ? "text-emerald-400" : "text-rose-400"} />
              <Metric label="Max DD" value={`${m.maxDrawdownPct.toFixed(1)}%`} accent="text-amber-400" />
              <Metric label="Hit Rate" value={`${m.winRatePct}%`} />
              <Metric label="Final NAV" value={m.finalNav.toFixed(4)} />
            </div>

            <section className="aq-glass rounded-lg overflow-hidden">
              <PanelHeader
                title={`NAV · ${detail.id}`}
                right={
                  <span className="text-[10px] text-slate-500">
                    {detail.factorName} on {detail.engine} · L/S top-3 of {detail.universe} · 2bps costs
                  </span>
                }
              />
              <div className="p-3 pt-4">
                <AreaChart values={detail.nav.map((x) => x.nav)} stroke={positive ? "#34d399" : "#f87171"} />
              </div>
              {"pricingBasis" in detail && (detail as unknown as { pricingBasis?: string }).pricingBasis && (
                <p className="px-4 pb-3 text-[9px] text-slate-600">
                  pricing basis: {(detail as unknown as { pricingBasis?: string }).pricingBasis}
                </p>
              )}
            </section>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <section className="aq-glass rounded-lg overflow-hidden">
                <PanelHeader title="Drawdown %" />
                <div className="p-3">
                  <MultiLine series={[{ label: "dd", values: drawdown, color: "#f87171" }]} />
                </div>
              </section>

              <section className="aq-glass rounded-lg overflow-hidden">
                <PanelHeader title="Execution Trace · trace.py" />
                <div className="p-4 space-y-2.5 text-[11px]">
                  {detail.trace.map((t, i) => (
                    <div key={i} className="flex gap-3">
                      <span className="text-slate-600 tabular-nums font-mono shrink-0">{fmtClock(t.ts)}</span>
                      <div className="min-w-0">
                        <p className="text-slate-200 font-mono font-medium">{t.span}</p>
                        <p className="text-slate-500 text-[10px]">{t.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </>
        ) : (
          <section className="aq-glass rounded-lg p-10 text-center text-slate-600 text-[11px]">
            {error ? "start the backend to load runs" : "select a run…"}
          </section>
        )}
      </div>
    </div>
  );
}
