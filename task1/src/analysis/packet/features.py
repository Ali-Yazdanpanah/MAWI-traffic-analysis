"""Non-distribution packet plots: counts, mixes, and raw size summaries."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from analysis.bootstrap import load_packets
from analysis.plot_common import (
    FIGSIZE,
    FIGSIZE_BAR,
    FIGSIZE_WIDE,
    MIN_GROUP_PACKETS,
    PROTOCOL_COLORS,
    TOP_APP_PROTOS,
    save_figure,
    title_suffix,
)
from analysis.results_paths import PACKET_FEATURES, resolve_results_dir

COLOR_BAR = "#4f46e5"


def plot_transport_proto_bar(packets: pd.DataFrame, out_dir: Path) -> Path:
    counts = packets["transport_proto"].fillna("unknown").value_counts().sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=FIGSIZE_BAR)
    counts.plot(kind="barh", ax=ax, color=COLOR_BAR, edgecolor="white")
    ax.set_xlabel("packet count")
    ax.set_ylabel("transport_proto")
    ax.set_title(f"L4 / transport mix {title_suffix(packets)}")
    ax.grid(True, axis="x", alpha=0.3)
    path = out_dir / "transport_proto_bar.png"
    save_figure(fig, path)
    return path


def plot_app_proto_top10_bar(packets: pd.DataFrame, out_dir: Path) -> Path:
    labeled = packets["app_proto"].fillna("unknown")
    counts = labeled.value_counts().head(10).sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=FIGSIZE_BAR)
    counts.plot(kind="barh", ax=ax, color=COLOR_BAR, edgecolor="white")
    ax.set_xlabel("packet count")
    ax.set_ylabel("app_proto")
    ax.set_title(f"Application mix (top 10) {title_suffix(packets)}")
    ax.grid(True, axis="x", alpha=0.3)
    path = out_dir / "app_proto_top10_bar.png"
    save_figure(fig, path)
    return path


def plot_ip_version_bar(packets: pd.DataFrame, out_dir: Path) -> Path:
    version = packets["ip_version"].map({4: "IPv4", 6: "IPv6"}).fillna("unknown")
    counts = version.value_counts().sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    counts.plot(kind="barh", ax=ax, color=COLOR_BAR, edgecolor="white")
    ax.set_xlabel("packet count")
    ax.set_ylabel("ip_version")
    ax.set_title(f"IPv4 vs IPv6 {title_suffix(packets)}")
    ax.grid(True, axis="x", alpha=0.3)
    path = out_dir / "ip_version_bar.png"
    save_figure(fig, path)
    return path


def _frame_size_by_proto(
    packets: pd.DataFrame,
    proto_col: str,
    *,
    out_dir: Path,
    filename: str,
    title_label: str,
    top_n: int | None,
) -> Path:
    work = packets[[proto_col, "frame_len"]].copy()
    work[proto_col] = work[proto_col].fillna("unknown")
    work["frame_len"] = pd.to_numeric(work["frame_len"], errors="coerce")
    work = work.dropna()
    work = work[work["frame_len"] > 0]

    counts = work[proto_col].value_counts()
    if top_n is not None:
        keep = counts.head(top_n).index
        work = work[work[proto_col].isin(keep)]
        counts = counts.loc[keep]

    eligible = counts[counts >= MIN_GROUP_PACKETS].index.tolist()
    work = work[work[proto_col].isin(eligible)]
    if work.empty:
        fig, ax = plt.subplots(figsize=FIGSIZE)
        ax.text(0.5, 0.5, "No protocol groups with enough packets", ha="center", va="center")
        ax.set_title(f"Frame size by {title_label} {title_suffix(packets)}")
        path = out_dir / filename
        save_figure(fig, path)
        return path

    order = work.groupby(proto_col)["frame_len"].median().sort_values().index.tolist()
    data = [work.loc[work[proto_col] == p, "frame_len"].to_numpy() for p in order]

    fig, ax = plt.subplots(figsize=FIGSIZE_WIDE)
    ax.boxplot(data, labels=order, vert=False, patch_artist=True)
    ax.set_xscale("log")
    ax.set_xlabel("frame_len (bytes, log scale)")
    ax.set_ylabel(title_label)
    ax.set_title(f"Frame size by {title_label} {title_suffix(packets)}")
    ax.grid(True, axis="x", alpha=0.3)
    path = out_dir / filename
    save_figure(fig, path)
    return path


def plot_control_vs_data_bar(packets: pd.DataFrame, out_dir: Path) -> Path:
    counts = (
        packets["packet_role"]
        .fillna("other")
        .value_counts()
        .reindex(["control", "data", "other"], fill_value=0)
        .astype(int)
    )
    counts = counts[counts > 0].sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=FIGSIZE_BAR)
    colors = [PROTOCOL_COLORS.get(str(idx), COLOR_BAR) for idx in counts.index]
    counts.plot(kind="barh", ax=ax, color=colors, edgecolor="white")
    ax.set_xlabel("packet count")
    ax.set_ylabel("packet_role")
    ax.set_title(f"Control vs data packets {title_suffix(packets)}")
    ax.grid(True, axis="x", alpha=0.3)
    path = out_dir / "control_vs_data_bar.png"
    save_figure(fig, path)
    return path


def plot_frame_size_by_transport(packets: pd.DataFrame, out_dir: Path) -> Path:
    return _frame_size_by_proto(
        packets,
        "transport_proto",
        out_dir=out_dir,
        filename="frame_size_by_transport_proto.png",
        title_label="transport_proto",
        top_n=None,
    )


def plot_frame_size_by_app(packets: pd.DataFrame, out_dir: Path) -> Path:
    return _frame_size_by_proto(
        packets,
        "app_proto",
        out_dir=out_dir,
        filename="frame_size_by_app_proto.png",
        title_label="app_proto (top 10)",
        top_n=TOP_APP_PROTOS,
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
        category=PACKET_FEATURES,
        results_root=results_root,
    )
    return [
        plot_transport_proto_bar(packets, output),
        plot_app_proto_top10_bar(packets, output),
        plot_ip_version_bar(packets, output),
        plot_control_vs_data_bar(packets, output),
        plot_frame_size_by_transport(packets, output),
        plot_frame_size_by_app(packets, output),
    ]
