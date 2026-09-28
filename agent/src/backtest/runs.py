"""Shared run-record store + metrics math, used by engine.py's dispatcher
and every engines/ submodule. Split out from engine.py to avoid a circular
import (engine.py dispatches into engines/*, which need these helpers)."""

from __future__ import annotations

import math
import statistics
import time
import uuid

RUNS: dict[str, dict] = {}
COST_BPS = 2.0  # shared turnover-cost assumption across every engine


def compute_metrics(series: list[dict], daily_rets: list[float]) -> dict:
    """Real Sharpe/maxDD/annRet/winRate off a real daily-return series —
    every engine marks NAV differently, but the statistics are the same
    formulas everywhere."""
    mu = statistics.mean(daily_rets)
    sd = statistics.pstdev(daily_rets) or 1e-9
    sharpe = mu / sd * math.sqrt(252)
    peak, maxdd = 1.0, 0.0
    for m in series:
        peak = max(peak, m["nav"])
        maxdd = min(maxdd, m["nav"] / peak - 1)
    ann = (series[-1]["nav"]) ** (252 / max(1, len(series))) - 1
    wins = sum(1 for r in daily_rets if r > 0)
    return {
        "sharpe": round(sharpe, 2),
        "annRetPct": round(ann * 100, 2),
        "maxDrawdownPct": round(maxdd * 100, 2),
        "winRatePct": round(wins / len(daily_rets) * 100, 1),
        "finalNav": series[-1]["nav"],
    }


def new_run(engine: str, factor_id: str, factor_name: str, universe_n: int,
           series: list[dict], daily_rets: list[float], trace: list[dict],
           elapsed_ms: float, extra: dict | None = None) -> dict:
    rid = f"run_{uuid.uuid4().hex[:6]}"
    run = {
        "id": rid,
        "factorId": factor_id,
        "factorName": factor_name,
        "engine": engine,
        "universe": universe_n,
        "days": len(series),
        "createdAt": int(time.time() * 1000),
        "status": "completed",
        "elapsedMs": elapsed_ms,
        "metrics": compute_metrics(series, daily_rets),
        "nav": series,
        "trace": trace,
    }
    if extra:
        run.update(extra)
    RUNS[rid] = run
    return run
