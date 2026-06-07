"""Packet-level PDF and CCDF plots."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.bootstrap import load_packets
from analysis.plot_common import (
    FRAME_LEN_BINS,
    MIN_GROUP_PACKETS,
    PROTOCOL_COLORS,
    TOP_APP_PROTOS_OVERLAY,
    plot_ccdf,
    plot_pdf,
    plot_pdf_overlay,
    positive,
    title_suffix,
)
from analysis.results_paths import PACKET_DISTRIBUTION, resolve_results_dir


def _groups_by_column(
    packets: pd.DataFrame,
    column: str,
    *,
    top_n: int | None = None,
    only_labels: list[str] | None = None,
) -> dict[str, pd.Series]:
    work = packets[[column, "frame_len"]].copy()
    work[column] = work[column].fillna("unknown").astype(str)
    work["frame_len"] = pd.to_numeric(work["frame_len"], errors="coerce")
    work = work.dropna()
    work = work[work["frame_len"] > 0]

    counts = work[column].value_counts()
    if only_labels:
        keep = [label for label in only_labels if label in counts.index]
    elif top_n is not None:
        keep = counts.head(top_n).index.tolist()
    else:
        keep = counts.index.tolist()

    keep = [label for label in keep if counts.get(label, 0) >= MIN_GROUP_PACKETS]
    groups: dict[str, pd.Series] = {}
    for label in keep:
        groups[label] = work.loc[work[column] == label, "frame_len"]
    return groups


def plot_iat_pdf(packets: pd.DataFrame, out_dir: Path) -> Path:
    return plot_pdf(
        positive(packets["time_delta"]),
        out_path=out_dir / "iat_pdf.png",
        xlabel="inter-arrival time (s, log scale)",
        title=f"PDF — inter-arrival time {title_suffix(packets)}",
        log_x=True,
        log_y=True,
    )


def plot_frame_len_pdf(packets: pd.DataFrame, out_dir: Path) -> Path:
    return plot_pdf(
        positive(packets["frame_len"]),
        out_path=out_dir / "frame_len_pdf.png",
        xlabel="Frame length (bytes)",
        title=f"Packet size (PDF) {title_suffix(packets)}",
        bins=FRAME_LEN_BINS,
        color="#4C72B0",
    )


def plot_frame_len_pdf_data_only(packets: pd.DataFrame, out_dir: Path) -> Path:
    data = packets[packets["packet_role"] == "data"].copy()
    return plot_pdf(
        positive(data["frame_len"]),
        out_path=out_dir / "frame_len_pdf_data_only.png",
        xlabel="Frame length (bytes)",
        title=f"Packet size (PDF, data packets only) {title_suffix(data)}",
        bins=FRAME_LEN_BINS,
        color=PROTOCOL_COLORS["data"],
    )


def plot_frame_len_pdf_by_transport(packets: pd.DataFrame, out_dir: Path) -> Path:
    groups = _groups_by_column(packets, "transport_proto", only_labels=["tcp", "udp"])
    if not groups:
        groups = _groups_by_column(packets, "transport_proto", top_n=4)
    by_label = {label: positive(series) for label, series in groups.items()}
    return plot_pdf_overlay(
        by_label,
        out_path=out_dir / "frame_len_pdf_by_transport_proto.png",
        xlabel="Frame length (bytes)",
        title=f"Packet size by transport (PDF) {title_suffix(packets)}",
        bins=FRAME_LEN_BINS,
        legend_title="protocol",
    )


def plot_frame_len_pdf_control_vs_data(packets: pd.DataFrame, out_dir: Path) -> Path:
    groups = _groups_by_column(packets, "packet_role", only_labels=["control", "data"])
    by_label = {label: positive(series) for label, series in groups.items()}
    return plot_pdf_overlay(
        by_label,
        out_path=out_dir / "frame_len_pdf_control_vs_data.png",
        xlabel="Frame length (bytes)",
        title=f"Packet size — control vs data (PDF) {title_suffix(packets)}",
        bins=FRAME_LEN_BINS,
        legend_title="packet_role",
    )


def plot_frame_len_pdf_by_app(packets: pd.DataFrame, out_dir: Path) -> Path:
    groups = _groups_by_column(packets, "app_proto", top_n=TOP_APP_PROTOS_OVERLAY)
    by_label = {label: positive(series) for label, series in groups.items()}
    return plot_pdf_overlay(
        by_label,
        out_path=out_dir / "frame_len_pdf_by_app_proto.png",
        xlabel="Frame length (bytes)",
        title=f"Packet size by application (PDF) {title_suffix(packets)}",
        bins=FRAME_LEN_BINS,
        legend_title="app_proto",
    )


def plot_iat_ccdf(packets: pd.DataFrame, out_dir: Path) -> Path:
    return plot_ccdf(
        positive(packets["time_delta"]),
        out_path=out_dir / "iat_ccdf.png",
        xlabel="inter-arrival time (s, log scale)",
        title=f"CCDF — inter-arrival time {title_suffix(packets)}",
        log_x=True,
    )


def _plot_iat_ccdf_transport(packets: pd.DataFrame, out_dir: Path, proto: str) -> Path | None:
    labels = packets["transport_proto"].fillna("unknown").astype(str).str.lower()
    subset = packets.loc[labels == proto]
    values = positive(subset["time_delta"])
    if len(values) < MIN_GROUP_PACKETS:
        return None
    color = PROTOCOL_COLORS.get(proto, "#2563eb")
    return plot_ccdf(
        values,
        out_path=out_dir / f"iat_ccdf_{proto}.png",
        xlabel="inter-arrival time (s, log scale)",
        title=f"CCDF — inter-arrival time ({proto.upper()}) {title_suffix(subset)}",
        log_x=True,
        color=color,
    )


def plot_iat_ccdf_tcp(packets: pd.DataFrame, out_dir: Path) -> Path | None:
    return _plot_iat_ccdf_transport(packets, out_dir, "tcp")


def plot_iat_ccdf_udp(packets: pd.DataFrame, out_dir: Path) -> Path | None:
    return _plot_iat_ccdf_transport(packets, out_dir, "udp")


def plot_frame_len_ccdf(packets: pd.DataFrame, out_dir: Path) -> Path:
    return plot_ccdf(
        positive(packets["frame_len"]),
        out_path=out_dir / "frame_len_ccdf.png",
        xlabel="frame_len (bytes, log scale)",
        title=f"CCDF — frame size {title_suffix(packets)}",
        log_x=True,
    )


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
        category=PACKET_DISTRIBUTION,
        results_root=results_root,
    )
    paths = [
        plot_iat_pdf(packets, output),
        plot_frame_len_pdf(packets, output),
        plot_frame_len_pdf_data_only(packets, output),
        plot_frame_len_pdf_by_transport(packets, output),
        plot_frame_len_pdf_control_vs_data(packets, output),
        plot_frame_len_pdf_by_app(packets, output),
        plot_iat_ccdf(packets, output),
        plot_frame_len_ccdf(packets, output),
    ]
    for plot_fn in (plot_iat_ccdf_tcp, plot_iat_ccdf_udp):
        path = plot_fn(packets, output)
        if path is not None:
            paths.append(path)
    return paths
