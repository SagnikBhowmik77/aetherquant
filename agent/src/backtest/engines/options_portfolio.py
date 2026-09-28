"""options_portfolio engine — real Black-Scholes-priced covered-call
overlay on top of the same real long-short book as spot_basic.

There is no live options chain for this universe (no exchange quotes these
symbols' options in a way this app can fetch for free), so the premium is
priced theoretically off REAL realized volatility (trailing rolling stdev
of the book's own daily returns, annualized — same style of computation as
`_f_vol20` in factors/registry.py), via a standard closed-form
Black-Scholes ATM call formula (r=0, since no risk-free-rate source is
wired). This is real option-pricing math over a real volatility input, but
it is a theoretical fair value, NOT a live market quote — `pricingBasis` on
the run record says so explicitly rather than implying a real chain exists.

Simplification made explicit: this models pure premium harvesting (the
"volatility risk premium" a covered-call seller typically earns) added as
a small extra daily yield — it does NOT simulate assignment/exercise or
cap the book's upside, since there's no real strike price to be assigned
against without a live chain. `factor_id` labels the underlying long-short
book exactly as spot_basic does.
"""

from __future__ import annotations

import math
import statistics
import time

from ..long_short import long_short_daily_returns
from ..runs import new_run

VOL_WINDOW = 20
OPTION_TENOR_YEARS = 30 / 365
TRADING_DAYS_PER_TENOR = 21


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _atm_call_premium_frac(sigma_annual: float, tenor_years: float) -> float:
    """Black-Scholes ATM call premium as a fraction of spot (S=K, r=0
    collapses d1 = sigma*sqrt(T)/2, d2 = -d1 — no S/K numeric value needed
    for the ATM case)."""
    if sigma_annual <= 0 or tenor_years <= 0:
        return 0.0
    d1 = sigma_annual * math.sqrt(tenor_years) / 2
    return _norm_cdf(d1) - _norm_cdf(-d1)


def run(factor_id: str, days: int, hold: int = 3) -> dict:
    t0 = time.perf_counter()
    tss, base_rets, factor_name = long_short_daily_returns(factor_id, days, hold)

    overlay_rets: list[float] = []
    sigmas: list[float] = []
    for i, r in enumerate(base_rets):
        window = base_rets[max(0, i - VOL_WINDOW + 1): i + 1]
        sigma = statistics.pstdev(window) * math.sqrt(252) if len(window) > 1 else 0.0
        sigmas.append(sigma)
        premium_frac = _atm_call_premium_frac(sigma, OPTION_TENOR_YEARS)
        overlay_rets.append(r + premium_frac / TRADING_DAYS_PER_TENOR)

    nav = 1.0
    series: list[dict] = []
    for ts, r in zip(tss, overlay_rets):
        nav *= 1 + r
        series.append({"ts": ts, "nav": round(nav, 6)})

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    avg_sigma = statistics.mean(sigmas) if sigmas else 0.0
    trace = [
        {"ts": int(time.time() * 1000), "span": "base.long_short", "detail": f"{factor_name} long-short book, {len(series)} sessions"},
        {"ts": int(time.time() * 1000), "span": "vol.realized", "detail": f"trailing {VOL_WINDOW}d realized vol, annualized — avg {avg_sigma:.2%}"},
        {"ts": int(time.time() * 1000), "span": "options.black_scholes", "detail": f"ATM call, T={OPTION_TENOR_YEARS*365:.0f}d, r=0 — theoretical premium, no live chain"},
        {"ts": int(time.time() * 1000), "span": "engine.mark", "detail": f"options_portfolio marked {len(series)} NAVs in {elapsed_ms}ms"},
    ]
    return new_run("options_portfolio", factor_id, factor_name, 12, series, overlay_rets, trace, elapsed_ms,
                   extra={"pricingBasis": "theoretical fair value from realized volatility — no live options chain exists for this universe"})
