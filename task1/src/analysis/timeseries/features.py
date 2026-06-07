"""Time-series feature plots (not PDF/CCDF)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from analysis.bootstrap import load_packets
from analysis.plot_common import title_suffix
from analysis.results_paths import TIMESERIES_FEATURES, resolve_results_dir
from analysis.timeseries.iat_over_time import plot_iat_over_time
from analysis.timeseries.link_utilization import plot_link_utilization
from analysis.timeseries.protocol_stacked_area import (
    plot_app_protocol_stacked_area,
    plot_protocol_stacked_area,
)


def _maybe_plot_throughput_acf(packets: pd.DataFrame, *, out_path: Path, title: str) -> Path | None:
    try:
        from analysis.timeseries.throughput_acf import plot_throughput_acf
    except ImportError as exc:
        print(f"[timeseries] Skipping throughput ACF: {exc}", file=sys.stderr)
        return None
    try:
        return plot_throughput_acf(packets, out_path=out_path, title=title)
    except ImportError as exc:
        print(f"[timeseries] Skipping throughput ACF: {exc}", file=sys.stderr)
        return None


def plot_all(
    packets: pd.DataFrame | None = None,
    *,
    jsonl: str | Path | None = None,
    limit: int | None = None,
    results_root: str | Path | None = None,
) -> list[Path]:
    if packets is None:
        packets = load_packets(jsonl, limit=limit)
    if packets.empty:
        raise ValueError("No packets to plot")

    output = resolve_results_dir(
        len(packets),
        category=TIMESERIES_FEATURES,
        results_root=results_root,
    )
    paths = [
        plot_link_utilization(
            packets,
            out_path=output / "link_utilization.png",
            title=f"Link utilization {title_suffix(packets)}",
        ),
        plot_iat_over_time(
            packets,
            out_path=output / "iat_over_time.png",
            title=f"Mean packet IAT over time {title_suffix(packets)}",
        ),
        plot_protocol_stacked_area(
            packets,
            out_path=output / "protocol_stacked_area.png",
            title=f"Transport protocol share (100% stacked) {title_suffix(packets)}",
        ),
        plot_app_protocol_stacked_area(
            packets,
            out_path=output / "app_protocol_stacked_area.png",
            title=f"Application protocol share (100% stacked) {title_suffix(packets)}",
        ),
        _maybe_plot_throughput_acf(
            packets,
            out_path=output / "throughput_acf.png",
            title=f"Throughput ACF {title_suffix(packets)}",
        ),
    ]
    return [path for path in paths if path is not None]
