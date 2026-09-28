"""AetherQuant FastAPI server.

Run from repo root:
    python -m uvicorn api_server:app --app-dir aetherquant/agent --port 8700

Routes (all JSON camelCase, matching frontend/src/types.ts):
    GET  /api/health          system + engines + loaders (real per-loader status)
    GET  /api/alpha/list      full zoo bench
    GET  /api/alpha/{id}      one factor
    POST /api/alpha/bench     re-run the bench sweep
    GET  /api/runs            backtest run summaries
    GET  /api/runs/{id}       run detail (nav series + trace)
    POST /api/backtest        launch a real backtest
    POST /api/sentinel/scan   adversarial pre-flight on arbitrary code
    GET  /api/swarm/sessions  live swarm sessions
    GET  /api/quotes/live     real-time CN quote snapshot (sina/tencent)
    GET  /api/events          SSE telemetry stream
    POST /api/agent/chat      streaming agent reply (may launch real runs)
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.agent_loop import chat_reply, llm_provider, ollama_available
from src.backtest.engine import RUNS, best_run, engine_fleet, run_backtest, runs_summary, seed_runs
from src.factors.registry import (
    REGISTRY, ZOO_PLANNED_COUNTS, alpha_list, bench_all, last_benched_at, mean_ic, zoo_live_counts,
)
from src.market import (
    LOADERS, UNIVERSE, aggregate_vibe, live_quotes,
    load_all, loader_status, source_of,
)
from src.sentinel.scanner import full_scan
from src.stream import SESSION, hub, log, sse_format, telemetry_loop


@asynccontextmanager
async def lifespan(_app: FastAPI):
    t0 = time.perf_counter()
    load_all()
    bench_all()
    seed_runs()
    real_n = sum(1 for s in UNIVERSE if not source_of(s).startswith("synthetic"))
    wired_n = sum(1 for ok in loader_status().values() if ok)
    print(f"[aetherquant] bench + seed runs in {time.perf_counter() - t0:.1f}s "
          f"({len(REGISTRY)} factors, {len(RUNS)} runs, {real_n}/{len(UNIVERSE)} symbols real, "
          f"{wired_n}/{len(LOADERS)} loaders live this run)")
    task = asyncio.create_task(telemetry_loop())
    yield
    task.cancel()


app = FastAPI(title="AetherQuant API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


# ── models ─────────────────────────────────────────────────────────

class BacktestReq(BaseModel):
    factorId: str
    engine: str = "cross_market"
    days: int = 250


class ScanReq(BaseModel):
    target: str = "adhoc_snippet.py"
    code: str


class ChatReq(BaseModel):
    message: str


# ── REST ───────────────────────────────────────────────────────────

@app.get("/api/ping")
def ping():
    """Cheap liveness check for the host's health prober — no external
    calls, unlike /api/health."""
    return {"ok": True}


@app.get("/api/health")
def health():
    br = best_run()
    # every field here is a real computed number — no frontend-side
    # hardcoded fallbacks. alphaYieldPct/sharpe/maxDrawdownPct come from
    # whichever seeded backtest currently has the best Sharpe; vibeScore
    # is the real momentum/volume proxy off live prices.
    portfolio = {
        "alphaYieldPct": br["metrics"]["annRetPct"] if br else 0.0,
        "sharpe": br["metrics"]["sharpe"] if br else 0.0,
        "maxDrawdownPct": br["metrics"]["maxDrawdownPct"] if br else 0.0,
        "meanIC": mean_ic(),
        "vibeScore": aggregate_vibe(),
        "sourceRunId": br["id"] if br else None,
    }
    status = loader_status()
    return {
        "status": "ok",
        # real (cached) reachability check — "groq" | "ollama" | "none",
        # never a hardcoded flag. Chat falls back to a templated (but
        # real-data) reply when "none"; see src/agent_loop.py
        "llmProvider": llm_provider(),
        "ollamaActive": ollama_available(),
        "engines": engine_fleet(),
        # "online" comes from a genuine per-loader reachability probe
        # (see market.probe_all_loaders) — a loader only shows
        # green if it genuinely returned data just now, not a hardcoded flag
        "loaders": [{"name": n, "online": status.get(n, False), "wired": True} for n in LOADERS],
        "universe": UNIVERSE,
        # per-symbol data provenance, e.g. binance-live | eastmoney-cached |
        # yfinance-stale-cache | synthetic-fallback — surfaced in Settings
        # so it's never ambiguous whether a number is real market data
        "dataSources": {s: source_of(s) for s in UNIVERSE},
        # zooLiveCounts = factors that actually have code and are benched
        # right now (== len(REGISTRY)); zooPlannedCounts = the target roster
        # from the architecture spec with no implementation behind it yet —
        # never merged into one number so the UI can't imply they're all live
        "zooLiveCounts": zoo_live_counts(),
        "zooPlannedCounts": ZOO_PLANNED_COUNTS,
        "meanIC": mean_ic(),
        "lastBenchedAt": last_benched_at(),
        "portfolio": portfolio,
    }


@app.get("/api/quotes/live")
def quotes_live():
    """Real-time CN quote snapshot from sina (primary) / tencent (fallback).

    Distinct from the historical bars() pipeline on purpose — this is a
    single live tick per symbol, not a time series, so it's surfaced as
    its own feature rather than folded into the daily-bar backtesting data.
    """
    return live_quotes()


@app.get("/api/alpha/list")
def alpha_list_route():
    return alpha_list()


@app.get("/api/alpha/{fid}")
def alpha_get(fid: str):
    if fid not in REGISTRY:
        raise HTTPException(404, f"unknown factor: {fid}")
    return REGISTRY[fid]


@app.post("/api/alpha/bench")
def alpha_bench():
    t0 = time.perf_counter()
    bench_all()
    ms = round((time.perf_counter() - t0) * 1000)
    log("alpha", "bench_runner", f"full zoo re-bench: {len(REGISTRY)} factors in {ms}ms")
    return {"factors": len(REGISTRY), "elapsedMs": ms, "meanIC": mean_ic()}


@app.get("/api/runs")
def runs_route():
    return runs_summary()


@app.get("/api/runs/{rid}")
def run_get(rid: str):
    if rid not in RUNS:
        raise HTTPException(404, f"unknown run: {rid}")
    return RUNS[rid]


@app.post("/api/backtest")
def backtest(req: BacktestReq):
    if req.factorId not in REGISTRY:
        raise HTTPException(404, f"unknown factor: {req.factorId}")
    log("tool", "backtest_tool", f"launching {req.engine} run on {req.factorId} ({req.days}d)…")
    run = run_backtest(req.factorId, req.engine, req.days)
    m = run["metrics"]
    log("alpha", "backtest_tool",
        f"{run['id']} done in {run['elapsedMs']}ms — sharpe {m['sharpe']}, "
        f"ann {m['annRetPct']:+.1f}%, maxDD {m['maxDrawdownPct']:.1f}%")
    return run


@app.post("/api/sentinel/scan")
def sentinel_scan(req: ScanReq):
    results = full_scan(req.target, req.code)
    for r in results:
        if r["verdict"] != "pass":
            hub.publish("scan", r)
    log("sentinel", "sentinel",
        f"manual pre-flight {req.target}: " +
        ", ".join(f"{r['check']}={r['verdict']}" for r in results))
    return results


@app.get("/api/swarm/sessions")
def swarm_sessions():
    return [SESSION]


# ── SSE ────────────────────────────────────────────────────────────

@app.get("/api/events")
async def events():
    q = hub.subscribe()

    async def gen():
        try:
            yield sse_format("hello", {"ts": int(time.time() * 1000), "session": SESSION["id"]})
            while True:
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=15)
                    yield sse_format(event, data)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            hub.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── agent chat ─────────────────────────────────────────────────────

@app.post("/api/agent/chat")
async def chat(req: ChatReq):
    provider = await asyncio.to_thread(llm_provider)
    log("think", "orchestrator", f"chat: \"{req.message[:60]}\" — "
        f"{f'routing to {provider} (real LLM + tool-calling)' if provider != 'none' else 'no LLM reachable, using template fallback'}")
    return StreamingResponse(chat_reply(req.message, log), media_type="text/plain; charset=utf-8")


# ── static frontend (container deploys) ────────────────────────────
# The Docker image copies the built SPA into ./static. Mounted last so
# every /api route above takes precedence; absent in local dev, where
# Vite serves the frontend and proxies /api here.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
