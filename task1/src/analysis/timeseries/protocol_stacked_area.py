"""100% stacked area charts: traffic share over time by transport or application protocol."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from analysis.plot_common import FIGSIZE, save_figure, use_plot_style
from analysis.timeseries.resample import (
    binning_params,
    ip_proto_label,
    resolve_ip_proto_column,
    resolve_time_size_columns,
    style_time_xaxis,
    time_axis_values,
)


def resolve_app_proto_column(df: pd.DataFrame) -> str:
    for col in ("app_proto", "app.protocol", "application_proto"):
        if col in df.columns:
            return col
    raise KeyError("DataFrame must include 'app_proto' or equivalent application protocol column")


def _app_proto_label(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "unknown"
    label = str(value).strip().lower()
    return label if label else "unknown"


def _bytes_wide_by_label(
    df: pd.DataFrame,
    *,
    label_col: str,
    label_fn,
) -> tuple[pd.DataFrame, str, float, float]:
    """Resample frame bytes into a wide table (rows=time bins, columns=protocol labels)."""
    time_col, size_col = resolve_time_size_columns(df)
    work = df[[time_col, size_col, label_col]].copy()
    work[time_col] = pd.to_numeric(work[time_col], errors="coerce")
    work[size_col] = pd.to_numeric(work[size_col], errors="coerce")
    work = work.dropna(subset=[time_col, size_col])
    if work.empty:
        raise ValueError("No valid packets for protocol stacked area plot")

    work["timestamp"] = pd.to_datetime(work[time_col], unit="s", utc=False)
    work["proto_label"] = work[label_col].apply(label_fn)
    work = work.set_index("timestamp").sort_index()

    duration_s = float(work.index.max().timestamp() - work.index.min().timestamp())
    if duration_s <= 0:
        duration_s = 1e-6
    rule, _ma_window, _bin_seconds = binning_params(duration_s)

    bytes_wide = (
        work.groupby("proto_label")[size_col]
        .resample(rule)
        .sum()
        .unstack(level=0)
        .fillna(0)
    )
    return bytes_wide, rule, duration_s, _bin_seconds


def _to_percent_wide(bytes_wide: pd.DataFrame) -> pd.DataFrame:
    """Each row sums to 100% (share of traffic in that time bin)."""
    row_sums = bytes_wide.sum(axis=1)
    pct = bytes_wide.div(row_sums.where(row_sums > 0), axis=0) * 100.0
    return pct.fillna(0.0)


def _plot_percent_stacked_area(
    bytes_wide: pd.DataFrame,
    *,
    duration_s: float,
    rule: str,
    legend_title: str,
    title: str | None,
    default_title: str,
    out_path: Path | None,
) -> Path:
    pct_wide = _to_percent_wide(bytes_wide)
    x, xlabel, use_datetime = time_axis_values(pct_wide.index, duration_s)
    plot_df = pct_wide.copy()
    if not use_datetime:
        plot_df.index = x

    use_plot_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    plot_df.plot.area(ax=ax, stacked=True, alpha=0.85, linewidth=0.4, legend=False)

    ax.set_ylabel("Percentage of Traffic (%)")
    ax.set_xlabel(xlabel)
    ax.set_ylim(0, 100)
    ax.set_title(title if title is not None else default_title)
    ax.grid(True, alpha=0.3)
    if use_datetime:
        fig.autofmt_xdate()
    style_time_xaxis(ax, duration_s, use_datetime=use_datetime)
    ax.legend(
        title=legend_title,
        labels=list(pct_wide.columns),
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
        borderaxespad=0,
        fontsize=8,
    )
    fig.tight_layout()

    out_path = Path(out_path) if out_path is not None else Path("protocol_stacked_area.png")
    save_figure(fig, out_path)
    plt.style.use("default")
    return out_path


def plot_protocol_stacked_area(
    df: pd.DataFrame,
    *,
    out_path: Path | None = None,
    title: str | None = None,
) -> Path:
    """100% stacked area of traffic share by ip.proto / transport protocol."""
    proto_col = resolve_ip_proto_column(df)
    bytes_wide, rule, duration_s, _bin_seconds = _bytes_wide_by_label(
        df, label_col=proto_col, label_fn=ip_proto_label
    )
    return _plot_percent_stacked_area(
        bytes_wide,
        duration_s=duration_s,
        rule=rule,
        legend_title="ip.proto",
        title=title,
        default_title=(
            f"Traffic share by transport protocol (100% stacked, bin={rule}, "
            f"duration={duration_s:.3f}s)"
        ),
        out_path=out_path,
    )


def plot_app_protocol_stacked_area(
    df: pd.DataFrame,
    *,
    out_path: Path | None = None,
    title: str | None = None,
) -> Path:
    """100% stacked area of traffic share by application-layer protocol."""
    app_col = resolve_app_proto_column(df)
    bytes_wide, rule, duration_s, _bin_seconds = _bytes_wide_by_label(
        df, label_col=app_col, label_fn=_app_proto_label
    )
    return _plot_percent_stacked_area(
        bytes_wide,
        duration_s=duration_s,
        rule=rule,
        legend_title="app_proto",
        title=title,
        default_title=(
            f"Traffic share by application protocol (100% stacked, bin={rule}, "
            f"duration={duration_s:.3f}s)"
        ),
        out_path=out_path,
    )
