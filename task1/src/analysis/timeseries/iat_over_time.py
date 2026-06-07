"""Average packet inter-arrival time (IAT) over time."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from analysis.plot_common import FIGSIZE, save_figure, use_plot_style
from analysis.timeseries.resample import (
    RELATIVE_MS_THRESHOLD_S,
    binning_params,
    resolve_time_size_columns,
    style_time_xaxis,
    time_axis_values,
)


def resolve_iat_column(df: pd.DataFrame) -> str:
    for col in ("time_delta", "frame.time_delta"):
        if col in df.columns:
            return col
    raise KeyError("DataFrame must include 'time_delta' or 'frame.time_delta'")


def prepare_iat_timeseries(df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Return packet table indexed by timestamp with positive IAT values."""
    time_col, _size_col = resolve_time_size_columns(df)
    iat_col = resolve_iat_column(df)

    work = df[[time_col, iat_col]].copy()
    work[time_col] = pd.to_numeric(work[time_col], errors="coerce")
    work["iat"] = pd.to_numeric(work[iat_col], errors="coerce")
    work = work.dropna(subset=[time_col, "iat"])
    work = work[work["iat"] > 0]
    if work.empty:
        raise ValueError("No valid positive IAT values for plot")

    work["timestamp"] = pd.to_datetime(work[time_col], unit="s", utc=False)
    work = work.set_index("timestamp").sort_index()
    duration_s = float(work.index.max().timestamp() - work.index.min().timestamp())
    if duration_s <= 0:
        duration_s = 1e-6
    return work, duration_s


def _iat_display_scale(duration_s: float, values: pd.Series) -> tuple[pd.Series, str]:
    """Use milliseconds on the y-axis for short captures."""
    if duration_s < RELATIVE_MS_THRESHOLD_S:
        return values * 1000.0, "Mean packet IAT (ms)"
    return values, "Mean packet IAT (s)"


def plot_iat_over_time(
    df: pd.DataFrame,
    *,
    out_path: Path | None = None,
    title: str | None = None,
) -> Path:
    """Plot mean packet IAT per resampled time bin with a moving average overlay."""
    work, duration_s = prepare_iat_timeseries(df)
    rule, ma_window, _bin_seconds = binning_params(duration_s)
    avg_iat = work["iat"].resample(rule).mean()
    ma_iat = avg_iat.rolling(window=ma_window, min_periods=1).mean()

    avg_iat, ylabel = _iat_display_scale(duration_s, avg_iat)
    ma_iat, _ = _iat_display_scale(duration_s, ma_iat)

    x, xlabel, use_datetime = time_axis_values(avg_iat.index, duration_s)

    use_plot_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(x, avg_iat.values, color="#4C72B0", alpha=0.35, linewidth=1.0, label="mean IAT per bin")
    ax.plot(
        x,
        ma_iat.values,
        color="#1a1a1a",
        linewidth=2.5,
        label=f"moving avg ({ma_window} bins)",
    )

    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    if title is None:
        title = (
            f"Mean packet IAT over time (bin={rule}, MA={ma_window}, "
            f"duration={duration_s:.3f}s, n={len(work):,} pkts)"
        )
    ax.set_title(title)
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    if use_datetime:
        fig.autofmt_xdate()
    style_time_xaxis(ax, duration_s, use_datetime=use_datetime)

    out_path = Path(out_path) if out_path is not None else Path("iat_over_time.png")
    save_figure(fig, out_path)
    plt.style.use("default")
    return out_path
