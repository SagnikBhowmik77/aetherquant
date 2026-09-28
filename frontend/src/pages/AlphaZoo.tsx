/* AlphaZoo — interactive factor grid with live IC, decay curves,
 * AST expressions, and one-click real backtests via the API. */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAetherStore } from "../stores/store";
import type { AlphaFactor, AlphaLifecycle, AlphaZooOrigin } from "../types";
import { AreaChart, Sparkline } from "../components/charts";
import { PanelHeader } from "../components/Terminal";

const ZOOS: Array<AlphaZooOrigin | "all"> = ["all", "qlib158", "alpha101", "gtja191", "academic", "vibe"];
const LIFECYCLES: Array<AlphaLifecycle | "all"> = ["all", "alive", "reversed", "dead"];

const LIFECYCLE_BADGE: Record<string, string> = {
  alive: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  reversed: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  dead: "text-slate-500 bg-slate-500/10 border-slate-600/30",
};

function Chip({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-2.5 py-1 rounded-md border text-[10px] font-medium tracking-[0.04em] uppercase transition-colors ${
        active
          ? "border-slate-500/70 bg-slate-700/50 text-slate-100"
          : "border-slate-700/60 text-slate-500 hover:text-slate-300 hover:border-slate-600"
      }`}
    >
      {label}
    </button>
  );
}

function FactorCard({ a, onOpen }: { a: AlphaFactor; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className="aq-glass rounded-lg p-4 text-left flex flex-col gap-2 transition-colors"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-slate-100 font-semibold text-xs truncate">{a.name}</span>
        <span className={`px-1.5 py-0.5 rounded border text-[9px] font-semibold uppercase shrink-0 ${LIFECYCLE_BADGE[a.lifecycle]}`}>
          {a.lifecycle}
        </span>
      </div>
      <code className="text-[10px] text-slate-500 leading-snug line-clamp-2 min-h-[2.2em]">{a.expression}</code>
      <div className="flex items-end justify-between gap-2 mt-auto">
        <div>
          <p className="text-[9px] uppercase tracking-[0.08em] text-slate-600">{a.zoo}</p>
          <p className={`text-base font-semibold font-mono tabular-nums ${a.ic >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {a.ic >= 0 ? "+" : ""}
            {a.ic.toFixed(4)}
          </p>
        </div>
        <Sparkline values={a.icHistory} width={110} height={32} stroke={a.ic >= 0 ? "#34d399" : "#f87171"} />
      </div>
    </button>
  );
}

function DetailDrawer({ a, onClose }: { a: AlphaFactor; onClose: () => void }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const launch = async () => {
    setBusy(true);
    setError(null);
    try {
      const run = await api.backtest(a.id);
      navigate(`/runs?run=${run.id}`);
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  };

  return (
    <aside className="aq-glass rounded-lg overflow-hidden flex flex-col w-full xl:w-[380px] shrink-0 self-start xl:sticky xl:top-0">
      <PanelHeader
        title={a.name}
        right={
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-xs px-1">
            ✕
          </button>
        }
      />
      <div className="p-4 flex flex-col gap-4 text-[11px]">
        <div>
          <p className="text-[9px] font-medium uppercase tracking-[0.08em] text-slate-500 mb-1">AST Expression</p>
          <code className="block text-slate-300 bg-[#0a0e14] border border-slate-800 rounded-lg p-3 leading-relaxed break-words">
            {a.expression}
          </code>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <p className="text-[9px] font-medium uppercase tracking-[0.08em] text-slate-600">IC</p>
            <p className={`font-semibold font-mono tabular-nums text-sm ${a.ic >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {a.ic >= 0 ? "+" : ""}
              {a.ic.toFixed(4)}
            </p>
          </div>
          <div>
            <p className="text-[9px] font-medium uppercase tracking-[0.08em] text-slate-600">ICIR</p>
            <p className="font-semibold font-mono tabular-nums text-sm text-slate-200">{a.icir.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-[9px] font-medium uppercase tracking-[0.08em] text-slate-600">Sentinel</p>
            <p className={`font-semibold text-sm ${a.sentinelPassed ? "text-emerald-400" : "text-rose-400"}`}>
              {a.sentinelPassed ? "PASS" : "FLAG"}
            </p>
          </div>
        </div>
        <div>
          <p className="text-[9px] font-medium uppercase tracking-[0.08em] text-slate-500 mb-1">IC Decay · rolling</p>
          <AreaChart values={a.icHistory} stroke={a.ic >= 0 ? "#34d399" : "#f87171"} />
        </div>
        <button
          onClick={launch}
          disabled={busy}
          className="rounded-lg bg-indigo-500/90 text-white py-2 text-[11px] font-semibold hover:bg-indigo-500 transition-colors disabled:opacity-50"
        >
          {busy ? "Engine running…" : "Run real backtest (cross_market)"}
        </button>
        {error && <p className="text-rose-400 text-[10px] break-words">{error}</p>}
        <p className="text-slate-600 text-[10px] leading-relaxed">
          Launches a genuine long-short backtest on the 12-symbol universe via POST /api/backtest — NAV,
          Sharpe, and trace land in RunDetail.
        </p>
      </div>
    </aside>
  );
}

export default function AlphaZoo() {
  const alphas = useAetherStore((s) => s.alphas);
  const zooPlannedCounts = useAetherStore((s) => s.zooPlannedCounts);
  const lastBenchedAt = useAetherStore((s) => s.lastBenchedAt);
  const [zoo, setZoo] = useState<(typeof ZOOS)[number]>("all");
  const [life, setLife] = useState<(typeof LIFECYCLES)[number]>("all");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...alphas]
      .filter((a) => (zoo === "all" || a.zoo === zoo) && (life === "all" || a.lifecycle === life))
      .filter((a) => !q || a.name.toLowerCase().includes(q) || a.id.includes(q) || a.expression.toLowerCase().includes(q))
      .sort((a, b) => Math.abs(b.ic) - Math.abs(a.ic));
  }, [alphas, zoo, life, query]);

  const open = alphas.find((a) => a.id === openId) ?? null;
  // real live breakdown, computed directly from the loaded factors —
  // the planned roster is shown separately so it can never look live
  const liveCensus = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const a of alphas) counts[a.zoo] = (counts[a.zoo] ?? 0) + 1;
    return Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(" · ");
  }, [alphas]);
  const plannedTotal = Object.values(zooPlannedCounts).reduce((a, b) => a + b, 0);
  const benchedAgo = lastBenchedAt ? Math.max(0, Math.round((Date.now() - lastBenchedAt) / 60000)) : null;

  return (
    <div className="flex flex-col gap-4">
      <section className="aq-glass rounded-lg p-4 flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <h1 className="text-sm font-semibold text-slate-100 tracking-tight">
            Alpha Zoo
          </h1>
          <p className="text-[10px] text-slate-500 mt-0.5">
            <span className="text-emerald-400 font-semibold">{alphas.length} live</span> — {liveCensus}
            {benchedAgo !== null && <span className="text-slate-600"> · real-benched {benchedAgo}m ago</span>}
          </p>
          {plannedTotal > 0 && (
            <p className="text-[9px] text-slate-600 mt-0.5">
              {plannedTotal} more factors are on the architecture roadmap but not implemented — not counted above
            </p>
          )}
        </div>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="search name / id / expression…"
          className="bg-[#0a0e14] border border-slate-700/60 rounded-lg px-3 py-1.5 text-[11px] text-slate-200 placeholder:text-slate-600 outline-none focus:border-indigo-400/50 w-56"
        />
        <div className="flex gap-1.5 flex-wrap">
          {ZOOS.map((z) => (
            <Chip key={z} label={z} active={zoo === z} onClick={() => setZoo(z)} />
          ))}
        </div>
        <div className="flex gap-1.5">
          {LIFECYCLES.map((l) => (
            <Chip key={l} label={l} active={life === l} onClick={() => setLife(l)} />
          ))}
        </div>
      </section>

      <div className="flex flex-col xl:flex-row gap-4 items-start">
        <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-3 flex-1 w-full">
          {filtered.map((a) => (
            <FactorCard key={a.id} a={a} onOpen={() => setOpenId(a.id)} />
          ))}
          {filtered.length === 0 && (
            <p className="text-slate-600 text-[11px] col-span-full py-10 text-center">
              no factors match this filter — only {alphas.length} factors are implemented right now,
              try clearing the search or lifecycle filter
            </p>
          )}
        </div>
        {open && <DetailDrawer a={open} onClose={() => setOpenId(null)} />}
      </div>
    </div>
  );
}
