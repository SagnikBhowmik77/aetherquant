/* Rolling SSE execution terminal — shared by Home and Agent/Swarm chat. */

import { useEffect, useMemo, useRef } from "react";
import { useAetherStore } from "../stores/store";
import type { LogEvent, LogLevel } from "../types";

const TERMINAL_TAIL = 120; // render only the visible tail — the full ring buffer stays in the store

export const LEVEL_STYLE: Record<LogLevel, { tag: string; cls: string }> = {
  info:     { tag: "INFO", cls: "text-slate-400" },
  tool:     { tag: "TOOL", cls: "text-indigo-400" },
  think:    { tag: "THNK", cls: "text-cyan-300" },
  warn:     { tag: "WARN", cls: "text-amber-400" },
  error:    { tag: "ERRR", cls: "text-rose-400" },
  sentinel: { tag: "SNTL", cls: "text-fuchsia-400" },
  alpha:    { tag: "ALFA", cls: "text-emerald-400" },
};

export const fmtClock = (ts: number) =>
  new Date(ts).toLocaleTimeString("en-GB", { hour12: false }) +
  "." +
  String(ts % 1000).padStart(3, "0").slice(0, 2);

function LogLine({ e }: { e: LogEvent }) {
  const s = LEVEL_STYLE[e.level];
  return (
    <div className="aq-log-in aq-row flex gap-2 leading-relaxed px-2 -mx-2 rounded">
      <span className="text-slate-600 tabular-nums shrink-0">{fmtClock(e.ts)}</span>
      <span className={`shrink-0 font-semibold ${s.cls}`}>[{s.tag}]</span>
      <span className="text-slate-500 shrink-0 w-28 truncate">{e.source}</span>
      <span className="text-slate-300 break-words min-w-0">{e.message}</span>
    </div>
  );
}

export function PanelHeader({ title, right }: { title: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-700/40">
      <h2 className="text-[11px] tracking-[0.08em] uppercase text-slate-400 font-semibold">
        {title}
      </h2>
      {right}
    </div>
  );
}

export function Terminal({ title = "Execution Stream · SSE /events" }: { title?: string }) {
  const allLogs = useAetherStore((s) => s.logs);
  const logs = useMemo(() => allLogs.slice(-TERMINAL_TAIL), [allLogs]);
  const paused = useAetherStore((s) => s.logsPaused);
  const toggle = useAetherStore((s) => s.toggleLogsPaused);
  const connected = useAetherStore((s) => s.connected);
  const dataSource = useAetherStore((s) => s.dataSource);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = bodyRef.current;
    if (el && !paused) el.scrollTop = el.scrollHeight;
  }, [logs, paused]);

  return (
    <section className="aq-glass rounded-lg overflow-hidden flex flex-col min-h-0 flex-1">
      <PanelHeader
        title={title}
        right={
          <div className="flex items-center gap-3">
            <span className={`flex items-center gap-1.5 text-[10px] font-medium ${connected ? "text-emerald-400" : "text-rose-400"}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-400 aq-pulse" : "bg-rose-500"}`} />
              {connected ? (dataSource === "live" ? "LIVE · API" : "LIVE · MOCK") : "DISCONNECTED"}
            </span>
            <button
              onClick={toggle}
              className="text-[10px] font-medium px-2.5 py-1 rounded border border-slate-600/60 text-slate-300 hover:bg-slate-700/40 hover:border-slate-500/60 transition-colors"
            >
              {paused ? "Resume" : "Pause"}
            </button>
          </div>
        }
      />
      <div
        ref={bodyRef}
        className="relative flex-1 min-h-0 overflow-y-auto aq-scroll px-4 py-3 font-mono text-[11px] space-y-0.5 bg-[#0a0e14]"
      >
        {logs.length === 0 && <p className="text-slate-600">awaiting stream…</p>}
        {logs.map((e) => (
          <LogLine key={e.id} e={e} />
        ))}
        <div className="flex gap-2 text-emerald-400">
          <span className="text-slate-600">{">"}</span>
          <span className="aq-caret">▊</span>
        </div>
      </div>
    </section>
  );
}
