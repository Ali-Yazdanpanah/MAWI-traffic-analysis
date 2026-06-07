"""Link utilization time-series with dynamic binning and moving average."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from analysis.plot_common import FIGSIZE, save_figure, use_plot_style
from analysis.timeseries.resample import (
    binning_params,
    bytes_to_mbps,
    prepare_packet_timeseries,
    style_time_xaxis,
    time_axis_values,
)


def plot_link_utilization(
    df: pd.DataFrame,
    *,
    out_path: Path | None = None,
    title: str | None = None,
) -> Path:
    """Plot link utilization (Mbps) with raw throughput and a moving average."""
    work, size_col, _time_col, duration_s = prepare_packet_timeseries(df)
    rule, ma_window, bin_seconds = binning_params(duration_s)
    bytes_per_bin = work[size_col].resample(rule).sum()
    mbps = bytes_to_mbps(bytes_per_bin, bin_seconds)
    ma_mbps = mbps.rolling(window=ma_window, min_periods=1).mean()

    x, xlabel, use_datetime = time_axis_values(mbps.index, duration_s)

    use_plot_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(x, mbps.values, color="#4C72B0", alpha=0.35, linewidth=1.0, label="raw throughput")
    ax.plot(
        x,
        ma_mbps.values,
        color="#1a1a1a",
        linewidth=2.5,
        label=f"moving avg ({ma_window} bins)",
    )

    ax.set_ylabel("Throughput (Mbps)")
    ax.set_xlabel(xlabel)
    if title is None:
        title = (
            f"Link utilization (bin={rule}, MA={ma_window}, "
            f"duration={duration_s:.3f}s, n={len(work):,} pkts)"
        )
    ax.set_title(title)
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    if use_datetime:
        fig.autofmt_xdate()
    style_time_xaxis(ax, duration_s, use_datetime=use_datetime)

    out_path = Path(out_path) if out_path is not None else Path("link_utilization.png")
    save_figure(fig, out_path)
    plt.style.use("default")
    return out_path
