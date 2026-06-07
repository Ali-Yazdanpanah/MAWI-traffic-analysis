"""Flow-level PDF and CCDF plots (duration, size, throughput).

Curated for network-traffic characterization: every flow metric is shown as a
log-log PDF (distribution shape) and a log-log CCDF (heavy-tail behaviour),
broken down by the mice/elephant size classes. Flow size additionally gets a
TCP-vs-UDP overlay, and flow duration a per-application CCDF. Linear-axis
variants are intentionally omitted: flow size/duration/throughput are
heavy-tailed, so linear axes hide the tail that matters for characterization.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analysis.bootstrap import elephant_byte_threshold, load_flows, load_packets
from analysis.plot_common import (
    log_bins,
    plot_ccdf,
    plot_ccdf_overlay,
    plot_pdf,
    plot_pdf_overlay,
)
from analysis.results_paths import FLOW_DISTRIBUTION, resolve_results_dir

_SIZE_CLASSES = ("mice", "elephant")

_FLOW_METRICS: dict[str, dict[str, Any]] = {
    "size": {
        "column": "byte_sum",
        "label": "flow size",
        "xlabel_log": "flow size (bytes, log scale)",
    },
    "duration": {
        "column": "duration",
        "label": "flow duration",
        "xlabel_log": "flow duration (s, log scale)",
    },
    "throughput": {
        "column": "throughput_bps",
        "label": "flow throughput",
        "xlabel_log": "throughput (bit/s, log scale)",
    },
}


def _flows_for_size_class(flows: pd.DataFrame, size_class: str | None) -> pd.DataFrame:
    if size_class is None:
        return flows
    labels = flows["flow_size_class"].fillna("unknown").astype(str).str.lower()
    return flows.loc[labels == size_class]


def _flow_title_suffix(
    flows: pd.DataFrame,
    packets: pd.DataFrame,
    *,
    all_flows: pd.DataFrame | None = None,
    size_class: str | None = None,
) -> str:
    n_flows = len(flows)
    n_packets = len(packets)
    if n_packets == 0:
        base = f"(flows={n_flows:,})"
    else:
        span = packets["time_epoch"].max() - packets["time_epoch"].min()
        base = f"(flows={n_flows:,}, packets={n_packets:,}, span={span:.3f}s)"
    if size_class is None:
        return base
    ref = all_flows if all_flows is not None else flows
    threshold = elephant_byte_threshold(ref["byte_sum"])
    if threshold is None:
        return f"{base}, {size_class}"
    return f"{base}, {size_class}, elephant≥{threshold:,.0f} B (P95)"


def _metric_stem(metric_id: str, size_class: str | None) -> str:
    if size_class is None:
        return f"flow_{metric_id}"
    return f"flow_{metric_id}_{size_class}"


def _metric_title_label(metric: dict[str, Any], size_class: str | None) -> str:
    if size_class is None:
        return str(metric["label"])
    return f"{metric['label']} ({size_class})"


def _positive_values(flows: pd.DataFrame, column: str) -> np.ndarray:
    values = pd.to_numeric(flows[column], errors="coerce").dropna().to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    return values[values > 0]


def _flow_groups(
    flows: pd.DataFrame,
    group_col: str,
    value_col: str,
    *,
    only_labels: list[str],
) -> dict[str, np.ndarray]:
    work = flows[[group_col, value_col]].copy()
    work[group_col] = work[group_col].fillna("unknown").astype(str).str.lower()
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    work = work.dropna()
    work = work[work[value_col] > 0]
    work = work[work[group_col].isin(only_labels)]

    groups: dict[str, np.ndarray] = {}
    for label in only_labels:
        subset = work.loc[work[group_col] == label, value_col].to_numpy()
        if len(subset) > 0:
            groups[label] = subset
    return groups


def _maybe_plot_pdf(
    flows: pd.DataFrame,
    packets: pd.DataFrame,
    out_dir: Path,
    metric_id: str,
    *,
    all_flows: pd.DataFrame,
    size_class: str | None,
) -> Path | None:
    metric = _FLOW_METRICS[metric_id]
    subset = _flows_for_size_class(flows, size_class)
    values = _positive_values(subset, metric["column"])
    if len(values) < 2:
        return None

    stem = _metric_stem(metric_id, size_class)
    suffix = _flow_title_suffix(subset, packets, all_flows=all_flows, size_class=size_class)
    label = _metric_title_label(metric, size_class)
    # Semi-log PDF (log-x, linear-y): reveals the distribution shape/mode; a
    # lognormal shows up as a symmetric bell. Heavy tails are characterized by
    # the companion CCDF, which stays log-log.
    return plot_pdf(
        values,
        out_path=out_dir / f"{stem}_pdf.png",
        xlabel=str(metric["xlabel_log"]),
        title=f"PDF — {label} {suffix}",
        log_x=True,
        log_y=False,
        bins=log_bins([values], n_bins=50),
    )


def _maybe_plot_ccdf(
    flows: pd.DataFrame,
    packets: pd.DataFrame,
    out_dir: Path,
    metric_id: str,
    *,
    all_flows: pd.DataFrame,
    size_class: str | None,
) -> Path | None:
    metric = _FLOW_METRICS[metric_id]
    subset = _flows_for_size_class(flows, size_class)
    values = _positive_values(subset, metric["column"])
    if len(values) < 2:
        return None

    stem = _metric_stem(metric_id, size_class)
    suffix = _flow_title_suffix(subset, packets, all_flows=all_flows, size_class=size_class)
    label = _metric_title_label(metric, size_class)
    return plot_ccdf(
        values,
        out_path=out_dir / f"{stem}_ccdf.png",
        xlabel=str(metric["xlabel_log"]),
        title=f"CCDF — {label} {suffix}",
        log_x=True,
    )


def _maybe_plot_size_by_transport(
    flows: pd.DataFrame,
    packets: pd.DataFrame,
    out_dir: Path,
    *,
    all_flows: pd.DataFrame,
    size_class: str | None,
) -> Path | None:
    subset = _flows_for_size_class(flows, size_class)
    groups = _flow_groups(subset, "transport_proto", "byte_sum", only_labels=["tcp", "udp"])
    if len(groups) < 2:
        return None

    metric = _FLOW_METRICS["size"]
    stem = _metric_stem("size", size_class)
    suffix = _flow_title_suffix(subset, packets, all_flows=all_flows, size_class=size_class)
    label = _metric_title_label(metric, size_class)
    return plot_pdf_overlay(
        groups,
        out_path=out_dir / f"{stem}_pdf_by_transport_proto.png",
        xlabel="Flow size (bytes, log scale)",
        title=f"{label.capitalize()} by transport (PDF) {suffix}",
        legend_title="transport_proto",
        log_x=True,
        log_y=False,
        n_bins=50,
    )


def _maybe_plot_duration_ccdf_by_app(
    flows: pd.DataFrame,
    packets: pd.DataFrame,
    out_dir: Path,
) -> Path | None:
    groups = _flow_groups(flows, "app_proto", "duration", only_labels=["http", "tls", "dns"])
    if len(groups) < 2:
        return None

    suffix = _flow_title_suffix(flows, packets)
    return plot_ccdf_overlay(
        groups,
        out_path=out_dir / "flow_duration_ccdf_by_app_proto.png",
        xlabel="Flow duration (s, log scale)",
        title=f"Flow duration by application (CCDF) {suffix}",
        legend_title="app_proto",
        log_x=True,
    )


def _append(path: Path | None, paths: list[Path]) -> None:
    if path is not None:
        paths.append(path)


def plot_all(
    packets: pd.DataFrame | None = None,
    flows: pd.DataFrame | None = None,
    *,
    jsonl: str | Path | None = None,
    limit: int | None = None,
    results_root: str | Path | None = None,
) -> list[Path]:
    if packets is None:
        packets = load_packets(jsonl, limit=limit)
    if flows is None:
        flows = load_flows(packets)
    if flows.empty:
        raise ValueError("No flows to plot")

    output = resolve_results_dir(
        len(packets),
        category=FLOW_DISTRIBUTION,
        results_root=results_root,
    )

    paths: list[Path] = []
    all_classes: tuple[str | None, ...] = (None, *_SIZE_CLASSES)

    for metric_id in ("size", "duration", "throughput"):
        for size_class in all_classes:
            _append(
                _maybe_plot_pdf(flows, packets, output, metric_id, all_flows=flows, size_class=size_class),
                paths,
            )
            _append(
                _maybe_plot_ccdf(flows, packets, output, metric_id, all_flows=flows, size_class=size_class),
                paths,
            )

    for size_class in all_classes:
        _append(
            _maybe_plot_size_by_transport(flows, packets, output, all_flows=flows, size_class=size_class),
            paths,
        )

    _append(_maybe_plot_duration_ccdf_by_app(flows, packets, output), paths)

    return paths
