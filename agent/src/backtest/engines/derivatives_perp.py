"""derivatives_perp engine — real perpetual-futures funding-rate carry,
using Binance's free keyless historical funding-rate endpoint
(market.funding_rates, backed by `_fetch_binance_funding` in market.py).

Strategy: long spot + short perp on BTC-USDT and ETH-USDT. Assumed
delta-neutral (spot gain/loss roughly offsets the short perp leg, basis
risk not modeled — no live perp price feed exists here, only funding
history), so the daily return realized is the real historical funding
payments collected (funding is paid ~every 8h; grouped into daily sums),
minus a small assumed carry/rebalance cost. No synthetic fallback here on
purpose — if Binance's funding endpoint is unreachable, this engine raises
rather than inventing a carry number (same honesty rule as every other
real loader in this app).
"""

from __future__ import annotations

import time

from ...factors.registry import get_factor
from ...market import DAY_MS, funding_rates
from ..runs import new_run

CARRY_COST_BPS = 0.5  # modest assumed daily cost of staying delta-neutral
LEGS = ["BTC-USDT", "ETH-USDT"]


def _daily_funding(symbol: str) -> dict[int, float]:
    """Sum real funding payments (paid ~every 8h) into a real per-day total."""
    out: dict[int, float] = {}
    for f in funding_rates(symbol):
        day = f["ts"] // DAY_MS
        out[day] = out.get(day, 0.0) + f["rate"]
    return out


def run(factor_id: str, days: int) -> dict:
    t0 = time.perf_counter()
    factor = get_factor(factor_id)
    factor_name = factor["name"] if factor else factor_id
    per_leg = {s: _daily_funding(s) for s in LEGS}
    if all(not d for d in per_leg.values()):
        raise RuntimeError(
            "derivatives_perp: no real funding-rate data available "
            "(Binance funding endpoint unreachable from this deployment) — "
            "this engine has no synthetic fallback by design")

    common_days = sorted(set.intersection(*(set(d) for d in per_leg.values())) or
                         set.union(*(set(d) for d in per_leg.values())))
    common_days = common_days[-days:] if len(common_days) > days else common_days

    daily_rets: list[float] = []
    tss: list[int] = []
    for day in common_days:
        rates = [per_leg[s].get(day, 0.0) for s in LEGS]
        carry = sum(rates) / len(rates) - CARRY_COST_BPS / 1e4
        daily_rets.append(carry)
        tss.append(day * DAY_MS)

    if not daily_rets:
        raise RuntimeError("derivatives_perp: funding data present but produced no overlapping days")

    nav = 1.0
    series: list[dict] = []
    for ts, r in zip(tss, daily_rets):
        nav *= 1 + r
        series.append({"ts": ts, "nav": round(nav, 6)})

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    n_real = sum(1 for d in per_leg.values() if d)
    trace = [
        {"ts": int(time.time() * 1000), "span": "funding.fetch", "detail": f"Binance fundingRate, {n_real}/{len(LEGS)} legs real ({', '.join(LEGS)})"},
        {"ts": int(time.time() * 1000), "span": "carry.compute", "detail": f"long spot + short perp, {len(daily_rets)} real daily funding sums, delta-neutral assumption"},
        {"ts": int(time.time() * 1000), "span": "engine.mark", "detail": f"derivatives_perp marked {len(series)} NAVs in {elapsed_ms}ms"},
    ]
    return new_run("derivatives_perp", factor_id, factor_name, len(LEGS), series, daily_rets, trace, elapsed_ms,
                   extra={"pricingBasis": "real historical Binance perp funding, assumes delta-neutral spot/perp (basis risk not modeled)"})
