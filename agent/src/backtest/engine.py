"""Backtest engine dispatcher.

Each of the 5 named engines now runs genuinely distinct real math instead
of sharing one implementation (see engines/ submodules) — engine_fleet()'s
`sharedImplementation` flag reflects this honestly per engine.
"""

from __future__ import annotations

import time

from ..market import UNIVERSE
from .engines import cross_market, derivatives_perp, multi_asset, options_portfolio
from .long_short import long_short_daily_returns
from .runs import RUNS, new_run

ENGINES = ["spot_basic", "cross_market", "options_portfolio", "multi_asset", "derivatives_perp"]


def _run_spot_basic(factor_id: str, engine: str, days: int, hold: int) -> dict:
    """Cross-sectional long-short factor backtest — rank the universe on a
    factor signal each day, go long the top bucket and short the bottom
    bucket (equal weight), charge costs on turnover, mark NAV daily. Real
    portfolio math on the live-priced universe."""
    t0 = time.perf_counter()
    tss, daily_rets, factor_name = long_short_daily_returns(factor_id, days, hold)

    nav = 1.0
    series: list[dict] = []
    for ts, r in zip(tss, daily_rets):
        nav *= 1 + r
        series.append({"ts": ts, "nav": round(nav, 6)})

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    trace = [
        {"ts": int(time.time() * 1000), "span": "loader.fetch", "detail": f"{len(UNIVERSE)} symbols x {days}d via loader fallback chain"},
        {"ts": int(time.time() * 1000), "span": "factor.compute", "detail": f"{factor_name} — {len(series)} cross-sections, AST-gated ops only"},
        {"ts": int(time.time() * 1000), "span": "portfolio.solve", "detail": f"L/S top-{hold} equal weight, cost 2bps on turnover"},
        {"ts": int(time.time() * 1000), "span": "engine.mark", "detail": f"{engine} marked {len(series)} NAVs in {elapsed_ms}ms"},
    ]
    return new_run(engine, factor_id, factor_name, len(UNIVERSE), series, daily_rets, trace, elapsed_ms)


def run_backtest(factor_id: str, engine: str = "cross_market",
                 days: int = 250, hold: int = 3) -> dict:
    """Dispatch to the engine-specific real implementation. `factor_id` is
    still accepted/labeled for every engine (API contract + RunDetail/Compare
    display), but only spot_basic's ranking actually uses the factor signal
    to drive positions — the other 4 engines have their own real strategy
    logic (see engines/ submodules) and reference the factor only as a label."""
    if engine == "cross_market":
        return cross_market.run(factor_id, days)
    if engine == "multi_asset":
        return multi_asset.run(factor_id, days)
    if engine == "options_portfolio":
        return options_portfolio.run(factor_id, days, hold)
    if engine == "derivatives_perp":
        return derivatives_perp.run(factor_id, days)
    return _run_spot_basic(factor_id, "spot_basic", days, hold)


def seed_runs() -> None:
    """Pre-populate the run store so RunDetail/Compare have history.

    Each seed runs independently — derivatives_perp in particular has no
    synthetic fallback by design (see engines/derivatives_perp.py) and can
    genuinely raise if Binance's funding endpoint is unreachable from this
    deployment; one real data-availability failure shouldn't crash startup
    for the other 4 engines."""
    seeds = [
        ("q158_roc20", "cross_market", 250),
        ("a101_042", "spot_basic", 250),
        ("acad_pead", "multi_asset", 320),
        ("vibe_momo_7", "derivatives_perp", 180),
        ("a101_rev5", "options_portfolio", 250),
    ]
    for fid, eng, days in seeds:
        try:
            run_backtest(fid, eng, days)
        except Exception as e:
            print(f"[aetherquant.backtest] seed run failed for engine={eng} factor={fid}: {e}")


def best_run() -> dict | None:
    """The highest-Sharpe run so far — used as a dashboard input."""
    if not RUNS:
        return None
    return max(RUNS.values(), key=lambda r: r["metrics"]["sharpe"])


def runs_summary() -> list[dict]:
    out = []
    for r in sorted(RUNS.values(), key=lambda x: x["createdAt"], reverse=True):
        out.append({k: r[k] for k in
                    ("id", "factorId", "factorName", "engine", "universe",
                     "days", "createdAt", "status", "elapsedMs", "metrics")})
    return out


def engine_fleet() -> list[dict]:
    """The 5 named engines each now run genuinely distinct real strategy
    logic (see engines/ submodule per engine) — sharedImplementation is
    False across the board; it stays as a field (rather than being removed)
    so the honesty story is explicit in the API, not just implied by absence."""
    kinds = {"spot_basic": "spot", "cross_market": "composite", "options_portfolio": "options",
             "multi_asset": "multi-asset", "derivatives_perp": "derivatives"}
    fleet = []
    for name in ENGINES:
        runs = [r for r in RUNS.values() if r["engine"] == name]
        fleet.append({
            "name": name,
            "kind": kinds[name],
            "running": bool(runs),
            "activeRuns": len(runs),
            "lastSharpe": runs[-1]["metrics"]["sharpe"] if runs else 0.0,
            "sharedImplementation": False,
        })
    return fleet
