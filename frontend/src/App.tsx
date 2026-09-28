/* App shell — sidebar nav + routed pages over the ambient grid. */

import { useEffect } from "react";
import { HashRouter, NavLink, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import AgentChat from "./pages/AgentChat";
import AlphaZoo from "./pages/AlphaZoo";
import RunDetail from "./pages/RunDetail";
import Compare from "./pages/Compare";
import DagCanvas from "./pages/DagCanvas";
import Settings from "./pages/Settings";
import { startStream, stopStream } from "./lib/sseClient";
import { selectLiveSwarmCount, useAetherStore } from "./stores/store";

const NAV = [
  { to: "/", label: "Dashboard", icon: "◈" },
  { to: "/agent", label: "Agent / Swarm", icon: "⌬" },
  { to: "/zoo", label: "AlphaZoo", icon: "α" },
  { to: "/runs", label: "RunDetail", icon: "▤" },
  { to: "/compare", label: "Compare", icon: "⇄" },
  { to: "/dag", label: "DAG Canvas", icon: "⬡" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

function Sidebar() {
  const connected = useAetherStore((s) => s.connected);
  const dataSource = useAetherStore((s) => s.dataSource);
  const liveSwarms = useAetherStore(selectLiveSwarmCount);
  const eventsPerSec = useAetherStore((s) => s.health.eventsPerSec);

  return (
    <aside className="w-52 shrink-0 border-r border-slate-800/80 bg-[#0c1119] flex flex-col">
      <div className="px-4 py-4 border-b border-slate-800/80">
        <h1 className="text-sm font-bold tracking-tight text-slate-100">
          AetherQuant
        </h1>
        <p className="text-[9px] font-medium text-slate-500 tracking-[0.16em] uppercase mt-0.5">Agentic Alpha Terminal</p>
      </div>

      <nav className="flex-1 py-3 space-y-0.5 px-2">
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2 rounded-md text-[11.5px] font-medium transition-colors ${
                isActive
                  ? "bg-slate-800/70 text-slate-100"
                  : "text-slate-500 hover:text-slate-300 hover:bg-slate-800/40"
              }`
            }
          >
            <span className="w-4 text-center text-slate-600">{n.icon}</span>
            {n.label}
            {n.to === "/agent" && liveSwarms > 0 && (
              <span className="ml-auto text-[9px] px-1.5 rounded-full bg-emerald-500/10 text-emerald-400 tabular-nums font-mono">
                {liveSwarms}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-slate-800/80 space-y-1.5 text-[10px]">
        <div className="flex items-center gap-1.5">
          <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-400 aq-pulse" : "bg-rose-500"}`} />
          <span className={`font-medium ${connected ? "text-emerald-400" : "text-rose-400"}`}>
            {connected ? (dataSource === "live" ? "API LIVE" : "MOCK LIVE") : dataSource.toUpperCase()}
          </span>
        </div>
        <p className="text-slate-600 tabular-nums font-mono">{eventsPerSec.toLocaleString()} events/s · v0.1.0</p>
      </div>
    </aside>
  );
}

export default function App() {
  useEffect(() => {
    void startStream();
    return stopStream;
  }, []);

  return (
    <HashRouter>
      <div className="aq-grid-bg h-full flex overflow-hidden">
        <Sidebar />
        <main className="flex-1 min-w-0 overflow-y-auto aq-scroll p-4">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/agent" element={<AgentChat />} />
            <Route path="/zoo" element={<AlphaZoo />} />
            <Route path="/runs" element={<RunDetail />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/dag" element={<DagCanvas />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </HashRouter>
  );
}
