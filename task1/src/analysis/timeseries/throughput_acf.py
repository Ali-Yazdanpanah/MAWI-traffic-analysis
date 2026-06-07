"""Autocorrelation (ACF) of 1-second network throughput."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from analysis.plot_common import FIGSIZE, save_figure, use_plot_style
from analysis.timeseries.resample import bytes_to_mbps, prepare_packet_timeseries

ACF_BIN_SECONDS = 1.0
ACF_LAGS = 100


def plot_throughput_acf(
    df: pd.DataFrame,
    *,
    out_path: Path | None = None,
    title: str | None = None,
    lags: int = ACF_LAGS,
) -> Path:
    """Plot ACF of throughput resampled at 1-second bins (high resolution for periodic patterns)."""
    work, size_col, _time_col, _duration_s = prepare_packet_timeseries(df)
    bytes_per_sec = work[size_col].resample("1s").sum()
    if bytes_per_sec.empty:
        raise ValueError("No 1-second bins for ACF plot")
    full_index = pd.date_range(
        bytes_per_sec.index.min(),
        bytes_per_sec.index.max(),
        freq="1s",
    )
    bytes_per_sec = bytes_per_sec.reindex(full_index, fill_value=0)
    mbps = bytes_to_mbps(bytes_per_sec, ACF_BIN_SECONDS)

    if len(mbps) < 2:
        raise ValueError("Need at least two 1-second bins for ACF plot")

    effective_lags = min(lags, len(mbps) - 1)

    from statsmodels.graphics.tsaplots import plot_acf

    use_plot_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    plot_acf(mbps.values, lags=effective_lags, ax=ax, alpha=0.05)
    ax.set_xlabel("Lag (seconds)")
    ax.set_ylabel("Autocorrelation")
    if title is None:
        title = (
            f"Throughput autocorrelation (1s bins, lags={effective_lags}, "
            f"n={len(mbps)} bins)"
        )
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    out_path = Path(out_path) if out_path is not None else Path("throughput_acf.png")
    save_figure(fig, out_path)
    plt.style.use("default")
    return out_path
