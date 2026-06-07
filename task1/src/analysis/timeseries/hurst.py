"""Variance-time Hurst exponent estimate for throughput / count time series."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HurstResult:
    hurst: float
    slope: float
    intercept: float
    n_bins: int
    n_scales: int
    r_squared: float

    def summary_line(self) -> str:
        """One-line interpretation for reports and plot annotations."""
        h = self.hurst
        if h > 0.55:
            regime = "long-range dependence (burstiness)"
        elif h < 0.45:
            regime = "anti-persistent / smoother than Poisson"
        else:
            regime = "near-Poisson (short-memory)"
        return f"H ≈ {h:.2f} ({regime}; variance-time, {self.n_scales} scales, R²={self.r_squared:.2f})"


def estimate_hurst_variance_time(
    values: np.ndarray,
    *,
    min_blocks: int = 8,
    min_scales: int = 3,
) -> HurstResult | None:
    """
    Estimate Hurst exponent via log-log slope of block-sum variance vs aggregation level.

    For byte/count bins, independent (Poisson) traffic gives slope ≈ 1 ⇒ H ≈ 0.5.
    Super-linear growth (slope > 1) indicates positive long-range dependence (H > 0.5).
    """
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 32:
        return None

    ms: list[int] = []
    variances: list[float] = []
    max_exp = int(np.floor(np.log2(n))) - 2
    for exp in range(0, max_exp + 1):
        m = 2**exp
        n_blocks = n // m
        if n_blocks < min_blocks:
            break
        trimmed = x[: n_blocks * m]
        block_sums = trimmed.reshape(n_blocks, m).sum(axis=1)
        var = float(np.var(block_sums, ddof=1))
        if var <= 0:
            continue
        ms.append(m)
        variances.append(var)

    if len(ms) < min_scales:
        return None

    log_m = np.log(np.asarray(ms, dtype=float))
    log_v = np.log(np.asarray(variances, dtype=float))
    slope, intercept = np.polyfit(log_m, log_v, 1)
    predicted = slope * log_m + intercept
    ss_res = float(np.sum((log_v - predicted) ** 2))
    ss_tot = float(np.sum((log_v - np.mean(log_v)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return HurstResult(
        hurst=float(slope / 2.0),
        slope=float(slope),
        intercept=float(intercept),
        n_bins=n,
        n_scales=len(ms),
        r_squared=r_squared,
    )
