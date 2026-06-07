"""Shared time-series resampling helpers for packet DataFrames."""

from __future__ import annotations

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, MaxNLocator

from analysis.bootstrap import IP_PROTO_NAMES

HOUR_S = 3600.0
SIX_HOURS_S = 6 * HOUR_S
# Captures shorter than this use relative milliseconds on the x-axis.
RELATIVE_MS_THRESHOLD_S = 60.0
# Captures shorter than this (but >= ms threshold) use relative seconds.
RELATIVE_S_THRESHOLD_S = HOUR_S

def resolve_time_size_columns(df: pd.DataFrame) -> tuple[str, str]:
    if "frame.time_epoch" in df.columns:
        time_col = "frame.time_epoch"
    elif "time_epoch" in df.columns:
        time_col = "time_epoch"
    else:
        raise KeyError("DataFrame must include 'frame.time_epoch' or 'time_epoch'")

    if "frame.len" in df.columns:
        size_col = "frame.len"
    elif "frame_len" in df.columns:
        size_col = "frame_len"
    else:
        raise KeyError("DataFrame must include 'frame.len' or 'frame_len'")

    return time_col, size_col


def resolve_ip_proto_column(df: pd.DataFrame) -> str:
    if "ip.proto" in df.columns:
        return "ip.proto"
    if "ip_proto" in df.columns:
        return "ip_proto"
    raise KeyError("DataFrame must include 'ip.proto' or 'ip_proto'")


def ip_proto_label(proto_num: int | float | None) -> str:
    if proto_num is None or pd.isna(proto_num):
        return "unknown"
    num = int(proto_num)
    return IP_PROTO_NAMES.get(num, f"ipproto-{num}")


def capture_duration_seconds(df: pd.DataFrame, time_col: str) -> float:
    times = pd.to_numeric(df[time_col], errors="coerce").dropna()
    if times.empty:
        return 0.0
    duration = float(times.max() - times.min())
    return max(duration, 1e-6)


def binning_params(duration_s: float) -> tuple[str, int, float]:
    """
    Return (pandas resample rule, moving-average window in bins, bin width in seconds).

    Tiers:
      < 1 s        -> 1 ms bins
      1 s .. 60 s  -> 10 ms bins, MA window 20
      1 min .. 1 h -> 1 s bins, MA window 10
      > 1 h        -> 1 min bins, MA window 5
    """
    if duration_s < 1.0:
        return "1ms", 50, 0.001
    if duration_s <= 60.0:
        return "10ms", 20, 0.01
    if duration_s <= HOUR_S:
        return "1s", 10, 1.0
    return "1min", 5, 60.0


def bytes_to_mbps(bytes_per_bin: pd.Series | pd.DataFrame, bin_seconds: float) -> pd.Series | pd.DataFrame:
    if bin_seconds <= 0:
        raise ValueError("bin_seconds must be positive")
    return (bytes_per_bin * 8.0) / bin_seconds / 1e6


def prepare_packet_timeseries(df: pd.DataFrame) -> tuple[pd.DataFrame, str, str, float]:
    """Return indexed DataFrame with timestamp index, size column name, and duration (s)."""
    time_col, size_col = resolve_time_size_columns(df)
    work = df[[time_col, size_col]].copy()
    work[time_col] = pd.to_numeric(work[time_col], errors="coerce")
    work[size_col] = pd.to_numeric(work[size_col], errors="coerce")
    work = work.dropna(subset=[time_col, size_col])
    if work.empty:
        raise ValueError("No valid packets for time-series plot")

    work["timestamp"] = pd.to_datetime(work[time_col], unit="s", utc=False)
    work = work.set_index("timestamp").sort_index()
    duration_s = float(work.index.max().timestamp() - work.index.min().timestamp())
    if duration_s <= 0:
        duration_s = 1e-6
    return work, size_col, time_col, duration_s


def _relative_seconds(index: pd.DatetimeIndex) -> np.ndarray:
    t0 = index[0]
    return (index - t0).total_seconds().to_numpy(dtype=float)


def time_axis_values(
    time_index: pd.DatetimeIndex,
    duration_s: float,
) -> tuple[np.ndarray | pd.DatetimeIndex, str, bool]:
    """
    Choose x coordinates and label from capture duration.

    Returns (x_values, xlabel, use_datetime_axis).
    Short spans use relative ms/s; longer spans use wall-clock datetimes.
    """
    if duration_s < RELATIVE_MS_THRESHOLD_S:
        return _relative_seconds(time_index) * 1000.0, "Time (ms)", False
    if duration_s < RELATIVE_S_THRESHOLD_S:
        return _relative_seconds(time_index), "Time (s)", False
    return time_index, "Time", True


def style_time_xaxis(ax: plt.Axes, duration_s: float, *, use_datetime: bool) -> None:
    """Apply tick formatting after plotting (call once data are on the axes)."""
    if use_datetime:
        xmin, xmax = ax.get_xlim()
        # Guard against numeric unix/BMv2 seconds on a date axis (matplotlib ordinals are ~2e5).
        if xmax > 1_000_000 or xmin > 1_000_000:
            use_datetime = False

    if not use_datetime:
        ax.xaxis.set_major_locator(MaxNLocator(nbins=8, min_n_ticks=4))
        if duration_s < RELATIVE_MS_THRESHOLD_S:
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}"))
        elif duration_s < 10.0:
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.1f}"))
        else:
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0f}"))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha="center")
        return

    if duration_s <= SIX_HOURS_S:
        locator = mdates.AutoDateLocator(minticks=6, maxticks=12)
        formatter = mdates.DateFormatter("%H:%M")
    else:
        locator = mdates.AutoDateLocator(minticks=6, maxticks=12)
        formatter = mdates.DateFormatter("%Y-%m-%d\n%H:%M")

    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha="center")
