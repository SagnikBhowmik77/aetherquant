/* Settings — connection status, loader fleet, and the Sentinel
 * Playground: paste any Python and pre-flight it through the real
 * AST scanner on the backend. */

import { useEffect, useState } from "react";
import { api, type HealthData, type LiveQuote, type ScanResult } from "../lib/api";
import { useAetherStore } from "../stores/store";
import { PanelHeader } from "../components/Terminal";

const SAMPLE_BUGGY = `def signal(close, api):
    # oops: future data + unbounded orders + swallowed errors
    edge = ref(close, -1) / close - 1
    while True:
        api.submit_order(edge)
    try:
        api.flush()
    except Exception:
        pass
`;

const SAMPLE_CLEAN = `def signal(close, volume):
    momo = safe_div(close[-1], sma(close, 20)) - 1
    conviction = ts_rank(volume, 10)
    return momo * conviction
`;

const VERDICT_STYLE: Record<string, string> = {
  pass: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
  flag: "text-amber-400 border-amber-500/40 bg-amber-500/10",
  block: "text-rose-400 border-rose-500/40 bg-rose-500/10",
};

/* provenance strings look like "binance-live", "eastmoney-cached",
 * "yfinance-stale-cache", or "synthetic-fallback" — parse the loader name
 * out and color by freshness tier, since which of the 6 real loaders
 * actually served a symbol now varies per-symbol. */
function classifySource(src: string): { loader: string; cls: string } {
  if (src === "synthetic-fallback") {
    return { loader: "SIM", cls: "text-rose-400 border-rose-500/40 bg-rose-500/10" };
  }
  if (src.endsWith("-stale-cache")) {
    return { loader: src.slice(0, -"-stale-cache".length).toUpperCase(), cls: "text-amber-400 border-amber-500/40 bg-amber-500/10" };
  }
  if (src.endsWith("-cached")) {
    return { loader: src.slice(0, -"-cached".length).toUpperCase(), cls: "text-cyan-300 border-cyan-500/40 bg-cyan-500/10" };
  }
  if (src.endsWith("-live")) {
    return { loader: src.slice(0, -"-live".length).toUpperCase(), cls: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10" };
  }
  return { loader: src.toUpperCase(), cls: "text-slate-500 border-slate-700" };
}

export default function Settings() {
  const dataSource = useAetherStore((s) => s.dataSource);
  const connected = useAetherStore((s) => s.connected);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [quotes, setQuotes] = useState<Record<string, LiveQuote> | null>(null);
  const [code, setCode] = useState(SAMPLE_BUGGY);
  const [results, setResults] = useState<ScanResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.liveQuotes().then(setQuotes).catch(() => setQuotes(null));
  }, []);

  const scan = async () => {
    setBusy(true);
    setScanError(null);
    try {
      setResults(await api.sentinelScan("playground.py", code));
    } catch (e) {
      setScanError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {/* ── connection ── */}
      <section className="aq-glass rounded-lg overflow-hidden">
        <PanelHeader title="Connection" />
        <div className="p-4 grid grid-cols-2 sm:grid-cols-5 gap-4 text-[11px]">
          <div>
            <p className="text-[9px] uppercase tracking-wider text-slate-600">Data Source</p>
            <p className={`font-bold uppercase ${dataSource === "live" ? "text-emerald-400" : "text-amber-400"}`}>
              {dataSource === "live" ? "FastAPI · live" : dataSource}
            </p>
          </div>
          <div>
            <p className="text-[9px] uppercase tracking-wider text-slate-600">SSE Stream</p>
            <p className={`font-bold uppercase ${connected ? "text-emerald-400" : "text-rose-400"}`}>
              {connected ? "connected" : "down"}
            </p>
          </div>
          <div>
            <p className="text-[9px] uppercase tracking-wider text-slate-600">API</p>
            <p className="text-slate-300 font-semibold">/api → 127.0.0.1:8700</p>
          </div>
          <div>
            <p className="text-[9px] uppercase tracking-wider text-slate-600">Mean IC</p>
            <p className="text-slate-200 font-semibold font-mono tabular-nums">{health ? health.meanIC.toFixed(4) : "—"}</p>
          </div>
          <div>
            <p className="text-[9px] uppercase tracking-wider text-slate-600" title="Real reachability check — Groq (hosted, when GROQ_API_KEY is set) or Ollama (local). Chat uses genuine tool-calling on either, and a templated (but real-data) fallback when neither is reachable.">
              Chat LLM
            </p>
            <p className={`font-bold uppercase ${health?.llmProvider && health.llmProvider !== "none" ? "text-emerald-400" : "text-amber-400"}`}>
              {health?.llmProvider === "groq" ? "Groq · live" : health?.llmProvider === "ollama" ? "Ollama · live" : "template fallback"}
            </p>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
        {/* ── sentinel playground ── */}
        <section className="aq-glass rounded-lg overflow-hidden">
          <PanelHeader
            title="Sentinel Playground · real AST scan"
            right={
              <div className="flex gap-1.5">
                <button onClick={() => setCode(SAMPLE_BUGGY)} className="text-[9px] px-2 py-0.5 rounded border border-rose-500/30 text-rose-400 hover:bg-rose-500/10">
                  buggy sample
                </button>
                <button onClick={() => setCode(SAMPLE_CLEAN)} className="text-[9px] px-2 py-0.5 rounded border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10">
                  clean sample
                </button>
              </div>
            }
          />
          <div className="p-4 flex flex-col gap-3">
            <textarea
              value={code}
              onChange={(e) => setCode(e.target.value)}
              spellCheck={false}
              rows={10}
              className="bg-[#0a0e14] border border-slate-700/60 rounded-lg p-3 font-mono text-[11px] text-slate-200 leading-relaxed outline-none focus:border-indigo-400/50 resize-y"
            />
            <button
              onClick={scan}
              disabled={busy || dataSource !== "live"}
              className="rounded-lg bg-indigo-500/90 text-white py-2 text-[11px] font-semibold hover:bg-indigo-500 transition-colors disabled:opacity-40"
            >
              {busy ? "Scanning…" : "Pre-flight scan"}
            </button>
            {dataSource !== "live" && (
              <p className="text-[10px] text-amber-400">backend offline — the scanner runs server-side (POST /api/sentinel/scan)</p>
            )}
            {scanError && <p className="text-[10px] text-rose-400 break-words">{scanError}</p>}
            {results && (
              <div className="space-y-2">
                {results.map((r, i) => (
                  <div key={i} className="flex items-start gap-3 text-[11px]">
                    <span className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded border text-[9px] font-bold tracking-wider uppercase ${VERDICT_STYLE[r.verdict]}`}>
                      {r.verdict}
                    </span>
                    <div>
                      <p className="text-slate-300 font-semibold">{r.check}</p>
                      <p className="text-slate-500 text-[10px]">{r.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* ── loader fleet ── */}
        <section className="aq-glass rounded-lg overflow-hidden">
          <PanelHeader
            title={`Data Loaders · ${health ? health.loaders.filter((l) => l.online).length : 0}/${health ? health.loaders.length : "—"}`}
            right={<span className="text-[10px] text-slate-500">reachability probed live, re-checked every 5 min</span>}
          />
          <div className="p-4 grid grid-cols-2 sm:grid-cols-3 gap-2">
            {(health?.loaders ?? []).map((l) => (
              <div
                key={l.name}
                title={l.wired ? (l.online ? "served real data this run" : "did not serve data this run — either the fetch failed, or an earlier loader in its fallback chain already succeeded first") : "no fetch code calls this loader"}
                className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2 text-[11px]"
              >
                <span className={`h-1.5 w-1.5 rounded-full ${l.online ? "bg-emerald-400" : l.wired ? "bg-rose-500" : "bg-slate-600"}`} />
                <span className={`truncate ${l.wired ? "text-slate-300" : "text-slate-600"}`}>{l.name}</span>
                {!l.wired && <span className="ml-auto text-[8px] text-slate-600 shrink-0">not wired</span>}
              </div>
            ))}
            {!health && <p className="text-slate-600 text-[11px] col-span-full">backend offline — loader fleet unavailable</p>}
          </div>
          {health && (
            <div className="px-4 pb-4">
              <p className="text-[9px] uppercase tracking-wider text-slate-600 mb-1.5">
                Universe · data provenance
              </p>
              <div className="flex flex-wrap gap-1.5">
                {health.universe.map((s) => {
                  const src = health.dataSources[s] ?? "unknown";
                  const { loader, cls } = classifySource(src);
                  return (
                    <span
                      key={s}
                      title={src}
                      className="flex items-center gap-1.5 text-[9px] pl-2 pr-1.5 py-0.5 rounded border border-indigo-500/20 text-indigo-300/80"
                    >
                      {s}
                      <span className={`px-1 rounded border text-[8px] font-bold ${cls}`}>{loader}</span>
                    </span>
                  );
                })}
              </div>
              <p className="text-[9px] text-slate-600 mt-2">
                Badge = which real loader served that symbol this run (green = live fetch, cyan = disk cache
                &lt;6h old, amber = stale cache after a failed refetch, red SIM = no real source reachable,
                synthetic geometric-Brownian fallback)
              </p>
            </div>
          )}
        </section>
      </div>

      {/* ── live CN quotes — genuinely real-time, distinct from historical bars ── */}
      <section className="aq-glass rounded-lg overflow-hidden">
        <PanelHeader
          title="Live CN Quotes · sina / tencent"
          right={<span className="text-[10px] text-slate-500">real-time snapshot, not a time series</span>}
        />
        <div className="p-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
          {quotes && Object.keys(quotes).length > 0 ? (
            Object.entries(quotes).map(([symbol, q]) => {
              const chg = ((q.price - q.prevClose) / q.prevClose) * 100;
              return (
                <div key={symbol} className="rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2.5 text-[11px]">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-200 font-semibold">{q.name}</span>
                    <span className="text-[8px] uppercase tracking-wider text-indigo-300/70 border border-indigo-500/20 rounded px-1">
                      {q.source}
                    </span>
                  </div>
                  <p className="text-[9px] text-slate-600">{symbol}</p>
                  <p className={`text-base font-bold tabular-nums mt-1 ${chg >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {q.price.toFixed(2)}{" "}
                    <span className="text-[10px]">
                      ({chg >= 0 ? "+" : ""}
                      {chg.toFixed(2)}%)
                    </span>
                  </p>
                </div>
              );
            })
          ) : (
            <p className="text-slate-600 text-[11px] col-span-full">
              {health ? "sina and tencent both unreachable from this network right now" : "backend offline"}
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
