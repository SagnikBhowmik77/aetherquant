"""multi_asset engine — real long-only Markowitz minimum-variance portfolio
over the 12-symbol universe's historical return covariance.

Closed-form min-variance weights (w ∝ Σ⁻¹·1), clipped to ≥0 and renormalized
for a long-only book (no scipy constrained optimizer needed — the clip is a
standard, if approximate, way to get a long-only solution from the
unconstrained closed form). Rebalanced periodically off a trailing
covariance window; real portfolio return realized each day off actual
closes, with turnover cost charged only on rebalance days.

`factor_id` is accepted only for the API's factorId/factorName label — this
engine's weights come from the covariance matrix, not a factor signal.
"""

from __future__ import annotations

import time

import numpy as np

from ...factors.registry import get_factor
from ...market import UNIVERSE, bars
from ..runs import COST_BPS, new_run

REBAL_EVERY = 20
LOOKBACK = 60


def _min_variance_weights(returns_window: np.ndarray) -> np.ndarray:
    n = returns_window.shape[0]
    cov = np.cov(returns_window) + np.eye(n) * 1e-8
    try:
        inv = np.linalg.pinv(cov)
        ones = np.ones(n)
        w = inv @ ones
        w = w / (ones @ w)
    except np.linalg.LinAlgError:
        w = np.ones(n) / n
    w = np.clip(w, 0, None)
    total = w.sum()
    return w / total if total > 0 else np.ones(n) / n


def run(factor_id: str, days: int) -> dict:
    t0 = time.perf_counter()
    factor = get_factor(factor_id)
    factor_name = factor["name"] if factor else factor_id

    closes = {s: [x["close"] for x in bars(s)] for s in UNIVERSE}
    total = min(len(closes[s]) for s in UNIVERSE)
    start = max(LOOKBACK + 1, total - days - 1)

    weights = {s: 1.0 / len(UNIVERSE) for s in UNIVERSE}
    nav = 1.0
    series: list[dict] = []
    daily_rets: list[float] = []

    for i, t in enumerate(range(start, total - 1)):
        cost = 0.0
        if i % REBAL_EVERY == 0:
            window_start = max(1, t - LOOKBACK + 1)
            R = np.array([
                [closes[s][k] / closes[s][k - 1] - 1 for k in range(window_start, t + 1)]
                for s in UNIVERSE
            ])
            new_w = _min_variance_weights(R)
            new_weights = {s: float(new_w[i2]) for i2, s in enumerate(UNIVERSE)}
            cost = sum(abs(new_weights[s] - weights[s]) for s in UNIVERSE) / 2 * COST_BPS / 1e4
            weights = new_weights

        fwd = {s: closes[s][t + 1] / closes[s][t] - 1 for s in UNIVERSE}
        ret = sum(weights[s] * fwd[s] for s in UNIVERSE) - cost
        nav *= 1 + ret
        daily_rets.append(ret)
        series.append({"ts": bars(UNIVERSE[0])[t + 1]["ts"], "nav": round(nav, 6)})

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    top_weights = sorted(weights.items(), key=lambda kv: -kv[1])[:4]
    trace = [
        {"ts": int(time.time() * 1000), "span": "covariance.compute", "detail": f"{len(UNIVERSE)}-asset trailing {LOOKBACK}d covariance, numpy"},
        {"ts": int(time.time() * 1000), "span": "portfolio.solve", "detail": "closed-form long-only min-variance (Σ⁻¹·1, clipped ≥0, renormalized)"},
        {"ts": int(time.time() * 1000), "span": "rebalance", "detail": f"every {REBAL_EVERY}d, top weights: " + ", ".join(f"{s}={w:.2f}" for s, w in top_weights)},
        {"ts": int(time.time() * 1000), "span": "engine.mark", "detail": f"multi_asset marked {len(series)} NAVs in {elapsed_ms}ms"},
    ]
    return new_run("multi_asset", factor_id, factor_name, len(UNIVERSE), series, daily_rets, trace, elapsed_ms,
                   extra={"finalWeights": weights})
