"""Autocorrelation (ACF) of resampled network throughput with Hurst annotation."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from analysis.plot_common import FIGSIZE, save_figure, use_plot_style
from analysis.timeseries.hurst import HurstResult, estimate_hurst_variance_time
from analysis.timeseries.resample import binning_params, bytes_to_mbps, prepare_packet_timeseries

DEFAULT_ACF_LAGS = 100
MIN_BINS_FOR_ACF = 32


def throughput_mbps_series(df: pd.DataFrame) -> tuple[pd.Series, str, float, float]:
    """Return Mbps per bin, pandas resample rule, bin width (s), capture duration (s)."""
    work, size_col, _time_col, duration_s = prepare_packet_timeseries(df)
    rule, _ma_window, bin_seconds = binning_params(duration_s)
    bytes_per_bin = work[size_col].resample(rule).sum()
    if bytes_per_bin.empty:
        raise ValueError("No resampled bins for throughput series")

    full_index = pd.date_range(
        bytes_per_bin.index.min(),
        bytes_per_bin.index.max(),
        freq=rule,
    )
    bytes_per_bin = bytes_per_bin.reindex(full_index, fill_value=0)
    mbps = bytes_to_mbps(bytes_per_bin, bin_seconds)
    return mbps, rule, bin_seconds, duration_s


def plot_throughput_acf(
    df: pd.DataFrame,
    *,
    out_path: Path | None = None,
    title: str | None = None,
    lags: int = DEFAULT_ACF_LAGS,
    hurst_json_path: Path | None = None,
) -> tuple[Path, HurstResult | None]:
    """Plot ACF of throughput at adaptive bin width; annotate with Hurst when available."""
    mbps, rule, bin_seconds, duration_s = throughput_mbps_series(df)
    if len(mbps) < MIN_BINS_FOR_ACF:
        raise ValueError(
            f"Need at least {MIN_BINS_FOR_ACF} throughput bins for ACF plot "
            f"(got {len(mbps)} at rule={rule})"
        )

    hurst = estimate_hurst_variance_time(mbps.to_numpy())
    effective_lags = min(lags, len(mbps) - 1)

    from statsmodels.graphics.tsaplots import plot_acf

    use_plot_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    plot_acf(mbps.values, lags=effective_lags, ax=ax, alpha=0.05)
    ax.set_xlabel(f"Lag (bins of {rule} ≈ {bin_seconds * 1000:.0f} ms)" if bin_seconds < 1 else f"Lag (bins of {rule})")
    ax.set_ylabel("Autocorrelation")

    annotation_lines = [
        f"bins={len(mbps)}, bin={rule}, lags={effective_lags}, span={duration_s:.2f}s",
    ]
    if hurst is not None:
        annotation_lines.append(hurst.summary_line())
    ax.text(
        0.02,
        0.98,
        "\n".join(annotation_lines),
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=8.5,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.85},
    )

    if title is None:
        title = f"Throughput ACF (bin={rule}, n={len(mbps)} bins, span={duration_s:.2f}s)"
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    out_path = Path(out_path) if out_path is not None else Path("throughput_acf.png")
    save_figure(fig, out_path)
    plt.style.use("default")

    if hurst_json_path is not None and hurst is not None:
        hurst_json_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "hurst": hurst.hurst,
            "slope": hurst.slope,
            "r_squared": hurst.r_squared,
            "n_bins": hurst.n_bins,
            "n_scales": hurst.n_scales,
            "bin_rule": rule,
            "bin_seconds": bin_seconds,
            "duration_s": duration_s,
            "summary": hurst.summary_line(),
        }
        hurst_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return out_path, hurst
