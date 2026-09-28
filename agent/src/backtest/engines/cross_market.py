"""cross_market engine — real pairs mean-reversion across two genuinely
different markets, run on two legs simultaneously:
  - BTC-USDT / ETH-USDT (crypto, live via the Binance loader)
  - 600519.SH / 000858.SZ (CN A-share, yfinance-cached)

For each pair: rolling z-score of log(close_a / close_b) over a lookback
window; go long the underperformer / short the outperformer once |z|
crosses an entry threshold, flatten once z reverts near 0. Same turnover
cost model as spot_basic. The two legs' daily returns are averaged into
one NAV series — genuinely "cross-market" since it trades a crypto pair
and a CN-equity pair at once, not a single-market strategy with a label.

`factor_id` is accepted only for the API's factorId/factorName label
(RunDetail/Compare display) — this strategy's positions come from the
pair z-score, not from any factor signal.
"""

from __future__ import annotations

import math
import time

from ...factors.registry import get_factor
from ...market import bars
from ..runs import COST_BPS, new_run

LOOKBACK = 20
ENTRY_Z = 1.5
EXIT_Z = 0.3
PAIRS = [("BTC-USDT", "ETH-USDT"), ("600519.SH", "000858.SZ")]


def _pair_leg(sym_a: str, sym_b: str, days: int) -> tuple[list[int], list[float]]:
    ca = [x["close"] for x in bars(sym_a)]
    cb = [x["close"] for x in bars(sym_b)]
    n = min(len(ca), len(cb))
    start = max(LOOKBACK + 1, n - days - 1)
    ratio = [math.log(ca[i] / cb[i]) for i in range(n)]

    pos = 0  # +1 = long a / short b, -1 = short a / long b, 0 = flat
    rets: list[float] = []
    tss: list[int] = []
    for t in range(start, n - 1):
        window = ratio[max(0, t - LOOKBACK + 1): t + 1]
        mean = sum(window) / len(window)
        sd = (sum((x - mean) ** 2 for x in window) / len(window)) ** 0.5 or 1e-9
        z = (ratio[t] - mean) / sd

        new_pos = pos
        if z > ENTRY_Z:
            new_pos = -1
        elif z < -ENTRY_Z:
            new_pos = 1
        elif abs(z) < EXIT_Z:
            new_pos = 0
        cost = abs(new_pos - pos) * COST_BPS / 1e4
        pos = new_pos

        ret_a = ca[t + 1] / ca[t] - 1
        ret_b = cb[t + 1] / cb[t] - 1
        rets.append(pos * (ret_a - ret_b) / 2 - cost)
        tss.append(bars(sym_a)[t + 1]["ts"])
    return tss, rets


def run(factor_id: str, days: int) -> dict:
    t0 = time.perf_counter()
    factor = get_factor(factor_id)
    factor_name = factor["name"] if factor else factor_id

    ts_crypto, ret_crypto = _pair_leg(*PAIRS[0], days)
    ts_cn, ret_cn = _pair_leg(*PAIRS[1], days)
    m = min(len(ret_crypto), len(ret_cn))
    if m == 0:
        raise RuntimeError("cross_market: insufficient history for both pair legs")

    ret_crypto, ret_cn = ret_crypto[-m:], ret_cn[-m:]
    ts_use = ts_crypto[-m:]
    daily_rets = [(a + b) / 2 for a, b in zip(ret_crypto, ret_cn)]

    nav = 1.0
    series = []
    for ts, r in zip(ts_use, daily_rets):
        nav *= 1 + r
        series.append({"ts": ts, "nav": round(nav, 6)})

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    trace = [
        {"ts": int(time.time() * 1000), "span": "pairs.crypto", "detail": "BTC-USDT/ETH-USDT log-ratio z-score, 20d lookback"},
        {"ts": int(time.time() * 1000), "span": "pairs.cn_equity", "detail": "600519.SH/000858.SZ log-ratio z-score, 20d lookback"},
        {"ts": int(time.time() * 1000), "span": "portfolio.combine", "detail": f"equal-weighted {m} paired daily returns, entry|z|>{ENTRY_Z}, exit|z|<{EXIT_Z}, cost {COST_BPS}bps"},
        {"ts": int(time.time() * 1000), "span": "engine.mark", "detail": f"cross_market marked {len(series)} NAVs in {elapsed_ms}ms"},
    ]
    return new_run("cross_market", factor_id, factor_name, 4, series, daily_rets, trace, elapsed_ms)
