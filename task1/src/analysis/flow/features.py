"""Flow-level feature plots: flow counts and summaries (not PDF/CCDF)."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from analysis.bootstrap import load_flows, load_packets
from analysis.plot_common import FIGSIZE_BAR, PROTOCOL_COLORS, TOP_APP_PROTOS, save_figure, use_plot_style
from analysis.results_paths import FLOW_FEATURES, resolve_results_dir

COLOR_BAR = "#4f46e5"


def _flow_title_suffix(flows: pd.DataFrame, packets: pd.DataFrame) -> str:
    n_flows = len(flows)
    n_packets = len(packets)
    if n_packets == 0:
        return f"(flows={n_flows:,})"
    t0 = packets["time_epoch"].min()
    t1 = packets["time_epoch"].max()
    return f"(flows={n_flows:,}, packets={n_packets:,}, span={t1 - t0:.3f}s)"


def plot_flow_count_by_transport(flows: pd.DataFrame, packets: pd.DataFrame, out_dir: Path) -> Path:
    counts = (
        flows["transport_proto"].fillna("unknown").astype(str).str.lower().value_counts().sort_values(ascending=True)
    )
    fig, ax = plt.subplots(figsize=FIGSIZE_BAR)
    colors = [PROTOCOL_COLORS.get(str(idx), COLOR_BAR) for idx in counts.index]
    counts.plot(kind="barh", ax=ax, color=colors, edgecolor="white")
    ax.set_xlabel("flow count")
    ax.set_ylabel("transport_proto")
    ax.set_title(f"Flow count by transport {_flow_title_suffix(flows, packets)}")
    ax.grid(True, axis="x", alpha=0.3)
    path = out_dir / "flow_count_by_transport_proto.png"
    save_figure(fig, path)
    return path


def plot_flow_count_by_size_class(flows: pd.DataFrame, packets: pd.DataFrame, out_dir: Path) -> Path:
    counts = (
        flows["flow_size_class"].fillna("unknown").astype(str).str.lower().value_counts().sort_values(ascending=True)
    )
    fig, ax = plt.subplots(figsize=FIGSIZE_BAR)
    colors = [PROTOCOL_COLORS.get(str(idx), COLOR_BAR) for idx in counts.index]
    counts.plot(kind="barh", ax=ax, color=colors, edgecolor="white")
    ax.set_xlabel("flow count")
    ax.set_ylabel("flow_size_class")
    ax.set_title(f"Mice vs elephant flows (P95 byte_sum split) {_flow_title_suffix(flows, packets)}")
    ax.grid(True, axis="x", alpha=0.3)
    path = out_dir / "flow_count_by_size_class.png"
    save_figure(fig, path)
    return path


def plot_flow_size_vs_duration(flows: pd.DataFrame, packets: pd.DataFrame, out_dir: Path) -> Path:
    """Log-log hexbin of flow byte_sum vs duration — links size and lifetime."""
    work = flows[["duration", "byte_sum", "flow_size_class"]].copy()
    work["duration"] = pd.to_numeric(work["duration"], errors="coerce")
    work["byte_sum"] = pd.to_numeric(work["byte_sum"], errors="coerce")
    work = work.dropna(subset=["duration", "byte_sum"])
    work = work[(work["duration"] > 0) & (work["byte_sum"] > 0)]
    if work.empty:
        from analysis.plot_common import plot_empty_notice

        return plot_empty_notice(
            out_path=out_dir / "flow_size_vs_duration.png",
            title=f"Flow size vs duration {_flow_title_suffix(flows, packets)}",
            message="No flows with positive duration and byte_sum.",
        )

    use_plot_style()
    fig, ax = plt.subplots(figsize=(8, 5.5))
    hb = ax.hexbin(
        work["duration"].to_numpy(),
        work["byte_sum"].to_numpy(),
        xscale="log",
        yscale="log",
        gridsize=45,
        mincnt=1,
        cmap="YlOrRd",
        linewidths=0.2,
        edgecolors="face",
    )
    cbar = fig.colorbar(hb, ax=ax)
    cbar.set_label("flow count")

    mice = work["flow_size_class"].astype(str).str.lower() == "mice"
    elephants = work["flow_size_class"].astype(str).str.lower() == "elephant"
    if elephants.any():
        ax.scatter(
            work.loc[elephants, "duration"],
            work.loc[elephants, "byte_sum"],
            s=12,
            alpha=0.35,
            c="#E64B35",
            edgecolors="none",
            label=f"elephant (n={elephants.sum():,})",
            zorder=3,
        )
    if mice.any() and mice.sum() <= 5000:
        ax.scatter(
            work.loc[mice, "duration"],
            work.loc[mice, "byte_sum"],
            s=6,
            alpha=0.15,
            c="#4C72B0",
            edgecolors="none",
            label=f"mice (n={mice.sum():,})",
            zorder=2,
        )

    ax.set_xlabel("flow duration (s)")
    ax.set_ylabel("flow size (bytes)")
    ax.set_title(f"Flow size vs duration (log-log) {_flow_title_suffix(flows, packets)}")
    if elephants.any() or (mice.any() and mice.sum() <= 5000):
        ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, which="both", alpha=0.25)
    path = out_dir / "flow_size_vs_duration.png"
    save_figure(fig, path)
    plt.style.use("default")
    return path


def plot_flow_count_by_app(flows: pd.DataFrame, packets: pd.DataFrame, out_dir: Path) -> Path:
    labeled = flows["app_proto"].fillna("unknown").astype(str).str.lower()
    counts = labeled.value_counts().head(TOP_APP_PROTOS).sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=FIGSIZE_BAR)
    colors = [PROTOCOL_COLORS.get(str(idx), COLOR_BAR) for idx in counts.index]
    counts.plot(kind="barh", ax=ax, color=colors, edgecolor="white")
    ax.set_xlabel("flow count")
    ax.set_ylabel("app_proto")
    ax.set_title(f"Flow count by application (top {TOP_APP_PROTOS}) {_flow_title_suffix(flows, packets)}")
    ax.grid(True, axis="x", alpha=0.3)
    path = out_dir / "flow_count_by_app_proto.png"
    save_figure(fig, path)
    return path


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
        category=FLOW_FEATURES,
        results_root=results_root,
    )
    return [
        plot_flow_count_by_transport(flows, packets, output),
        plot_flow_count_by_size_class(flows, packets, output),
        plot_flow_size_vs_duration(flows, packets, output),
        plot_flow_count_by_app(flows, packets, output),
    ]
