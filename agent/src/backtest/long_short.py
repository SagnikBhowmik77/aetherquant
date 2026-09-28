"""Shared cross-sectional long-short factor backtest math — used directly
by spot_basic (engine.py) and as the base book for options_portfolio's
Black-Scholes overlay. Split out so options_portfolio doesn't need to
import engine.py (which imports the engines/ package -> circular)."""

from __future__ import annotations

import time

from ..factors.registry import get_factor, signal_at
from ..market import UNIVERSE, bars
from .runs import COST_BPS


def long_short_daily_returns(factor_id: str, days: int, hold: int = 3):
    """Returns (timestamps, daily_returns, factor_name) for a real
    cross-sectional long-short backtest: rank the universe on the factor
    signal each day, long the top bucket / short the bottom bucket, charge
    turnover cost, one day of forward real return per step."""
    factor = get_factor(factor_id)
    if factor is None:
        raise KeyError(f"unknown factor: {factor_id}")

    total = min(len(bars(s)) for s in UNIVERSE)
    start = max(120, total - days - 1)
    positions: set[str] = set()
    shorts: set[str] = set()
    daily_rets: list[float] = []
    tss: list[int] = []

    for t in range(start, total - 1):
        sig = signal_at(factor, t)
        ranked = sorted(UNIVERSE, key=lambda s: sig[s])
        new_short, new_long = set(ranked[:hold]), set(ranked[-hold:])

        turnover = len(new_long ^ positions) + len(new_short ^ shorts)
        cost = turnover / (2 * hold) * COST_BPS / 1e4
        positions, shorts = new_long, new_short

        fwd = {s: bars(s)[t + 1]["close"] / bars(s)[t]["close"] - 1 for s in UNIVERSE}
        ret = (sum(fwd[s] for s in positions) / hold
               - sum(fwd[s] for s in shorts) / hold) / 2 - cost
        daily_rets.append(ret)
        tss.append(bars(UNIVERSE[0])[t + 1]["ts"])

    return tss, daily_rets, factor["name"]
