/* ────────────────────────────────────────────────────────────
 * Home — the AetherQuant command dashboard.
 *
 *  ┌ metrics strip: yield / sharpe / IC / swarms / vibe / health
 *  ├ equity curve (SSE-fed)        ├ swarm pipeline (live DAG strip)
 *  ├ rolling execution terminal    ├ sentinel sandbox feed
 *  └ top alphas (IC decay sparklines) + engine fleet
 * ──────────────────────────────────────────────────────────── */

import { useMemo } from "react";
import { Link } from "react-router-dom";
import { selectLiveSwarmCount, useAetherStore } from "../stores/store";
import type { NodeStatus, SentinelVerdict, SwarmNode } from "../types";
import { AreaChart, Meter, Sparkline } from "../components/charts";
import { PanelHeader, Terminal } from "../components/Terminal";

const fmtUptime = (s: number) => {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

const fmtK = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));

const NODE_STYLE: Record<NodeStatus, { dot: string; ring: string; text: string }> = {
  idle:      { dot: "bg-slate-600",   ring: "border-slate-700",      text: "text-slate-500" },
  running:   { dot: "bg-indigo-400",  ring: "border-indigo-500/60",  text: "text-indigo-300" },
  streaming: { dot: "bg-cyan-400",    ring: "border-cyan-400/60",    text: "text-cyan-300" },
  blocked:   { dot: "bg-amber-400",   ring: "border-amber-500/60",   text: "text-amber-300" },
  done:      { dot: "bg-emerald-400", ring: "border-emerald-500/60", text: "text-emerald-300" },
  failed:    { dot: "bg-rose-500",    ring: "border-rose-500/60",    text: "text-rose-400" },
};

const VERDICT_STYLE: Record<SentinelVerdict, string> = {
  pass: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
  flag: "text-amber-400 border-amber-500/40 bg-amber-500/10",
  block: "text-rose-400 border-rose-500/40 bg-rose-500/10",
};

function StatCard({
  label,
  value,
  sub,
  accent = "text-slate-100",
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="aq-glass rounded-lg px-4 py-3 flex flex-col gap-1 min-w-0">
      <span className="text-[10px] font-medium tracking-[0.08em] uppercase text-slate-500">{label}</span>
      <span className={`text-xl font-semibold font-mono tabular-nums leading-none ${accent}`}>{value}</span>
      {sub && <span className="text-[10px] text-slate-500 truncate">{sub}</span>}
    </div>
  );
}

function MetricsStrip() {
  const metrics = useAetherStore((s) => s.metrics);
  const health = useAetherStore((s) => s.health);
  const liveSwarms = useAetherStore(selectLiveSwarmCount);
  const zooLive = useAetherStore((s) => s.alphas.length);

  const vibePct = (metrics.vibeScore + 1) * 50;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
      <StatCard
        label="Alpha Yield"
        value={`${metrics.alphaYieldPct >= 0 ? "+" : ""}${metrics.alphaYieldPct.toFixed(1)}%`}
        sub="annualized · net of costs"
        accent={metrics.alphaYieldPct >= 0 ? "text-emerald-400" : "text-rose-400"}
      />
      <StatCard
        label="Sharpe"
        value={metrics.sharpe.toFixed(2)}
        sub={`max DD ${metrics.maxDrawdownPct.toFixed(1)}%`}
        accent={metrics.sharpe >= 0 ? "text-slate-100" : "text-rose-400"}
      />
      <StatCard
        label="Mean IC"
        value={metrics.meanIC.toFixed(4)}
        sub={`${zooLive} factors live (real)`}
      />
      <StatCard
        label="Active Swarms"
        value={String(liveSwarms)}
        sub={`${health.ssePipes} SSE pipes live`}
      />
      <div className="aq-glass rounded-lg px-4 py-3 flex flex-col gap-1.5 min-w-0">
        <span
          className="text-[10px] font-medium tracking-[0.08em] uppercase text-slate-500"
          title="Real-data proxy: tanh(10d momentum + volume z-score) off live yfinance closes — not NLP news sentiment"
        >
          Vibe Sentiment
        </span>
        <span
          className={`text-xl font-semibold font-mono tabular-nums leading-none ${
            metrics.vibeScore >= 0 ? "text-emerald-400" : "text-rose-400"
          }`}
        >
          {metrics.vibeScore >= 0 ? "+" : ""}
          {metrics.vibeScore.toFixed(2)}
        </span>
        <Meter pct={vibePct} color={metrics.vibeScore >= 0 ? "#34d399" : "#f87171"} />
      </div>
      <div className="aq-glass rounded-lg px-4 py-3 flex flex-col gap-1.5 min-w-0">
        <span
          className="text-[10px] font-medium tracking-[0.08em] uppercase text-slate-500"
          title="real host CPU/RAM utilization via psutil — not simulated"
        >
          System · <span className="font-mono">{fmtUptime(health.uptimeSec)}</span>
        </span>
        <div className="flex items-center gap-2 text-[10px] text-slate-500">
          <span className="w-7">CPU</span>
          <Meter pct={health.cpuPct} />
          <span className="tabular-nums font-mono w-8 text-right text-slate-400">{health.cpuPct}%</span>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-slate-500">
          <span className="w-7">MEM</span>
          <Meter pct={health.memPct} color="#67e8f9" />
          <span className="tabular-nums font-mono w-8 text-right text-slate-400">{health.memPct}%</span>
        </div>
      </div>
    </div>
  );
}

function EquityPanel() {
  const dataSource = useAetherStore((s) => s.dataSource);
  const equity = useAetherStore((s) => s.equity);
  const nav = equity[equity.length - 1]?.nav ?? 1;
  const pnl = (nav - 1) * 100;

  return (
    <section className="aq-glass rounded-lg overflow-hidden flex flex-col">
      <PanelHeader
        title="Aggregate Equity · Live Paper P&L"
        right={
          <span className={`text-xs font-semibold font-mono tabular-nums ${pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            NAV {nav.toFixed(4)} ({pnl >= 0 ? "+" : ""}
            {pnl.toFixed(2)}%)
          </span>
        }
      />
      <div className="p-3 pt-4 flex-1">
        <AreaChart values={equity.map((m) => m.nav)} stroke={pnl >= 0 ? "#34d399" : "#f87171"} />
      </div>
      <p className="px-4 pb-3 text-[9px] text-slate-600">
        {dataSource === "live"
          ? "real forward-advancing paper portfolio (5 engines, equal-weighted) — marked live for crypto/CN, on cache refresh for US equities"
          : "mock telemetry — backend offline"}
      </p>
    </section>
  );
}

function SwarmNodeChip({ node }: { node: SwarmNode }) {
  const s = NODE_STYLE[node.status];
  return (
    <div className={`relative rounded-md border ${s.ring} bg-[#111827]/60 px-3 py-2 min-w-[128px]`}>
      <div className="flex items-center gap-1.5">
        <span className={`h-1.5 w-1.5 rounded-full ${s.dot} ${node.status !== "idle" ? "aq-pulse" : ""}`} />
        <span className={`text-[10px] font-semibold tracking-wide ${s.text}`}>{node.label}</span>
      </div>
      <p className="mt-1 text-[10px] text-slate-500 leading-tight truncate max-w-[160px]">{node.activity}</p>
      <p className="mt-1 text-[9px] text-slate-600 tabular-nums font-mono">
        {fmtK(node.tokensUsed)} tok · {node.toolCalls} calls
      </p>
    </div>
  );
}

function SwarmPanel() {
  const session = useAetherStore((s) => s.sessions.find((x) => x.id === s.activeSessionId) ?? s.sessions[0]);
  if (!session) return null;

  return (
    <section className="aq-glass rounded-lg overflow-hidden flex flex-col">
      <PanelHeader
        title={`Swarm DAG · ${session.id}`}
        right={
          <div className="flex items-center gap-2">
            {session.simulated && (
              <span
                className="text-[8px] font-semibold tracking-wide px-1.5 py-0.5 rounded border border-amber-500/30 text-amber-400/90 bg-amber-500/5"
                title="offline mock session — backend unreachable, so this DAG is placeholder data. With the backend live, every counter here is real pipeline telemetry and this badge disappears."
              >
                SIMULATED
              </span>
            )}
            <Link to="/dag" className="flex items-center gap-1.5 text-[10px] font-medium text-indigo-300 hover:text-indigo-200">
              open canvas ↗
            </Link>
          </div>
        }
      />
      <div className="p-4 flex-1 flex flex-col justify-center gap-3">
        <p className="text-[11px] text-slate-400 -mt-1">{session.title}</p>
        <div className="flex items-center gap-0 overflow-x-auto aq-scroll pb-2">
          {session.nodes.map((node, i) => {
            const edge = session.edges.find(
              (e) => e.from === node.id && e.to === session.nodes[i + 1]?.id,
            );
            const anyOutActive = session.edges.some((e) => e.from === node.id && e.active);
            return (
              <div key={node.id} className="flex items-center shrink-0">
                <SwarmNodeChip node={node} />
                {i < session.nodes.length - 1 && (
                  <div className="w-8 h-[2px] mx-0.5 rounded-full overflow-hidden">
                    <div
                      className={
                        edge?.active || anyOutActive ? "aq-flow h-full w-full" : "h-full w-full bg-slate-800"
                      }
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function SentinelPanel() {
  const scans = useAetherStore((s) => s.scans);
  const recent = scans.slice(-6).reverse();

  return (
    <section className="aq-glass rounded-lg overflow-hidden flex flex-col">
      <PanelHeader
        title="Sentinel Sandbox · Pre-flight"
        right={<span className="text-[10px] font-medium text-slate-500">adversarial scan: on</span>}
      />
      <div className="max-h-[320px] overflow-y-auto aq-scroll divide-y divide-slate-800/60">
        {recent.length === 0 && <p className="px-4 py-6 text-[11px] text-slate-600">no scans yet — sandbox armed…</p>}
        {recent.map((scan) => (
          <div key={scan.id} className="px-4 py-2.5 flex items-start gap-3 text-[11px]">
            <span
              className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded border text-[9px] font-semibold tracking-wide uppercase ${VERDICT_STYLE[scan.verdict]}`}
            >
              {scan.verdict}
            </span>
            <div className="min-w-0">
              <p className="text-slate-300 truncate font-mono text-[10.5px]">{scan.target}</p>
              <p className="text-slate-500 text-[10px]">
                <span className="text-slate-400">{scan.check}</span> — {scan.detail}
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

const LIFECYCLE_BADGE: Record<string, string> = {
  alive: "text-emerald-400 bg-emerald-500/10 border-emerald-500/30",
  reversed: "text-amber-400 bg-amber-500/10 border-amber-500/30",
  dead: "text-slate-500 bg-slate-500/10 border-slate-600/30",
};

function AlphaTable() {
  const alphas = useAetherStore((s) => s.alphas);
  // sorted copy is derived here (not in a store selector) — zustand v5
  // selectors must return stable references or they re-render forever
  const top = useMemo(
    () => [...alphas].sort((a, b) => Math.abs(b.ic) - Math.abs(a.ic)).slice(0, 6),
    [alphas],
  );

  return (
    <section className="aq-glass rounded-lg overflow-hidden xl:col-span-2">
      <PanelHeader
        title="Alpha Zoo · Top by |IC|"
        right={
          <Link to="/zoo" className="text-[10px] font-medium text-slate-500 hover:text-indigo-300">
            bench_runner · live ↗
          </Link>
        }
      />
      <div className="overflow-x-auto aq-scroll">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-left text-[9px] uppercase tracking-[0.08em] text-slate-500 border-b border-slate-700/40">
              <th className="px-4 py-2 font-semibold">Factor</th>
              <th className="px-3 py-2 font-semibold">Zoo</th>
              <th className="px-3 py-2 font-semibold hidden lg:table-cell">Expression (AST)</th>
              <th className="px-3 py-2 font-semibold text-right">IC</th>
              <th className="px-3 py-2 font-semibold">Decay</th>
              <th className="px-3 py-2 font-semibold">State</th>
            </tr>
          </thead>
          <tbody>
            {top.map((a) => (
              <tr key={a.id} className="border-b border-slate-800/50 aq-row transition-colors">
                <td className="px-4 py-2">
                  <span className="text-slate-200 font-semibold">{a.name}</span>
                  {!a.sentinelPassed && <span className="ml-1.5 text-rose-400" title="sentinel flag">⚑</span>}
                </td>
                <td className="px-3 py-2 text-slate-400">{a.zoo}</td>
                <td className="px-3 py-2 hidden lg:table-cell">
                  <code className="text-slate-500 text-[10px]">{a.expression.slice(0, 52)}{a.expression.length > 52 ? "…" : ""}</code>
                </td>
                <td className={`px-3 py-2 text-right tabular-nums font-mono font-semibold ${a.ic >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {a.ic >= 0 ? "+" : ""}
                  {a.ic.toFixed(4)}
                </td>
                <td className="px-3 py-2">
                  <Sparkline values={a.icHistory} stroke={a.ic >= 0 ? "#34d399" : "#f87171"} />
                </td>
                <td className="px-3 py-2">
                  <span className={`px-1.5 py-0.5 rounded border text-[9px] font-semibold uppercase ${LIFECYCLE_BADGE[a.lifecycle]}`}>
                    {a.lifecycle}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EngineFleet() {
  const engines = useAetherStore((s) => s.engines);
  const shared = engines.some((e) => e.sharedImplementation);
  return (
    <section className="aq-glass rounded-lg overflow-hidden">
      <PanelHeader
        title={`Engine Fleet · ${engines.length}`}
        right={
          shared ? (
            <span
              className="text-[9px] text-amber-400"
              title="all 5 currently run the same long-short backtest — engine-specific pricing/risk math isn't built yet"
            >
              share 1 real implementation
            </span>
          ) : null
        }
      />
      <div className="divide-y divide-slate-800/60">
        {engines.map((e) => (
          <div key={e.name} className="px-4 py-2.5 flex items-center gap-3 text-[11px]">
            <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${e.running ? "bg-emerald-400 aq-pulse" : "bg-slate-600"}`} />
            <div className="min-w-0 flex-1">
              <p className="text-slate-200 font-medium truncate">{e.name}</p>
              <p className="text-[9px] uppercase tracking-[0.08em] text-slate-500">{e.kind}</p>
            </div>
            <span className="text-slate-500 tabular-nums font-mono shrink-0">{e.activeRuns} runs</span>
            <span
              className={`tabular-nums font-mono font-semibold shrink-0 w-16 text-right ${
                e.lastSharpe >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {e.lastSharpe.toFixed(2)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function Home() {
  return (
    <div className="flex flex-col gap-4">
      <MetricsStrip />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <EquityPanel />
        <SwarmPanel />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 flex h-[380px]">
          <Terminal />
        </div>
        <SentinelPanel />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <AlphaTable />
        <EngineFleet />
      </div>
    </div>
  );
}
