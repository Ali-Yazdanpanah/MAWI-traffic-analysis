"""Flow-level PDF and CCDF plots (duration, size, throughput)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.bootstrap import load_flows, load_packets
from analysis.plot_common import (
    plot_ccdf,
    plot_ccdf_overlay,
    plot_pdf,
    plot_pdf_overlay,
    positive,
)
from analysis.results_paths import FLOW_DISTRIBUTION, resolve_results_dir


def _flow_title_suffix(flows: pd.DataFrame, packets: pd.DataFrame) -> str:
    n_flows = len(flows)
    n_packets = len(packets)
    if n_packets == 0:
        return f"(flows={n_flows:,})"
    t0 = packets["time_epoch"].min()
    t1 = packets["time_epoch"].max()
    return f"(flows={n_flows:,}, packets={n_packets:,}, span={t1 - t0:.3f}s)"


def _flow_positive(flows: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(flows[column], errors="coerce").dropna()
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


def plot_flow_duration_pdf(flows: pd.DataFrame, packets: pd.DataFrame, out_dir: Path) -> Path:
    suffix = _flow_title_suffix(flows, packets)
    return plot_pdf(
        positive(_flow_positive(flows, "duration")),
        out_path=out_dir / "flow_duration_pdf.png",
        xlabel="flow duration (s, log scale)",
        title=f"PDF — flow duration {suffix}",
        log_x=True,
        log_y=True,
    )


def plot_flow_duration_ccdf(flows: pd.DataFrame, packets: pd.DataFrame, out_dir: Path) -> Path:
    suffix = _flow_title_suffix(flows, packets)
    return plot_ccdf(
        positive(_flow_positive(flows, "duration")),
        out_path=out_dir / "flow_duration_ccdf.png",
        xlabel="flow duration (s, log scale)",
        title=f"CCDF — flow duration {suffix}",
        log_x=True,
    )


def plot_flow_size_pdf(flows: pd.DataFrame, packets: pd.DataFrame, out_dir: Path) -> Path:
    suffix = _flow_title_suffix(flows, packets)
    return plot_pdf(
        positive(_flow_positive(flows, "byte_sum")),
        out_path=out_dir / "flow_size_pdf.png",
        xlabel="flow size (bytes, log scale)",
        title=f"PDF — flow size (bytes) {suffix}",
        log_x=True,
        log_y=True,
    )


def plot_flow_size_ccdf(flows: pd.DataFrame, packets: pd.DataFrame, out_dir: Path) -> Path:
    suffix = _flow_title_suffix(flows, packets)
    return plot_ccdf(
        positive(_flow_positive(flows, "byte_sum")),
        out_path=out_dir / "flow_size_ccdf.png",
        xlabel="flow size (bytes, log scale)",
        title=f"CCDF — flow size (bytes) {suffix}",
        log_x=True,
    )


def plot_flow_throughput_pdf(flows: pd.DataFrame, packets: pd.DataFrame, out_dir: Path) -> Path:
    suffix = _flow_title_suffix(flows, packets)
    return plot_pdf(
        positive(_flow_positive(flows, "throughput_bps")),
        out_path=out_dir / "flow_throughput_pdf.png",
        xlabel="throughput (bit/s, log scale)",
        title=f"PDF — flow throughput {suffix}",
        log_x=True,
        log_y=True,
    )


def plot_flow_size_pdf_by_transport(flows: pd.DataFrame, packets: pd.DataFrame, out_dir: Path) -> Path:
    """Flow size PDF: TCP vs UDP (each normalized separately, log-log)."""
    suffix = _flow_title_suffix(flows, packets)
    groups = _flow_groups(
        flows, "transport_proto", "byte_sum", only_labels=["tcp", "udp"]
    )
    return plot_pdf_overlay(
        groups,
        out_path=out_dir / "flow_size_pdf_by_transport_proto.png",
        xlabel="Flow size (bytes, log scale)",
        title=f"Flow size by transport (PDF) {suffix}",
        legend_title="transport_proto",
        log_x=True,
        log_y=True,
        n_bins=50,
    )


def plot_flow_duration_ccdf_by_app(flows: pd.DataFrame, packets: pd.DataFrame, out_dir: Path) -> Path:
    """Flow duration CCDF: http, tls, dns."""
    suffix = _flow_title_suffix(flows, packets)
    groups = _flow_groups(
        flows, "app_proto", "duration", only_labels=["http", "tls", "dns"]
    )
    return plot_ccdf_overlay(
        groups,
        out_path=out_dir / "flow_duration_ccdf_by_app_proto.png",
        xlabel="Flow duration (s, log scale)",
        title=f"Flow duration by application (CCDF) {suffix}",
        legend_title="app_proto",
        log_x=True,
    )


def plot_flow_throughput_ccdf(flows: pd.DataFrame, packets: pd.DataFrame, out_dir: Path) -> Path:
    suffix = _flow_title_suffix(flows, packets)
    return plot_ccdf(
        positive(_flow_positive(flows, "throughput_bps")),
        out_path=out_dir / "flow_throughput_ccdf.png",
        xlabel="throughput (bit/s, log scale)",
        title=f"CCDF — flow throughput {suffix}",
        log_x=True,
    )


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
    return [
        plot_flow_duration_pdf(flows, packets, output),
        plot_flow_duration_ccdf(flows, packets, output),
        plot_flow_size_pdf(flows, packets, output),
        plot_flow_size_pdf_by_transport(flows, packets, output),
        plot_flow_size_ccdf(flows, packets, output),
        plot_flow_duration_ccdf_by_app(flows, packets, output),
        plot_flow_throughput_pdf(flows, packets, output),
        plot_flow_throughput_ccdf(flows, packets, output),
    ]
