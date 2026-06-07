"""Shared helpers for Task I matplotlib plots."""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings(
    "ignore",
    message="Unable to import Axes3D",
    category=UserWarning,
    module=r"matplotlib\.projections",
)

DPI = 150
FIGSIZE = (8, 5)
FIGSIZE_BAR = (8, 5)
FIGSIZE_WIDE = (10, 5)
HIST_BINS = 80
FRAME_LEN_BINS = np.linspace(0, 1600, HIST_BINS + 1)
MIN_GROUP_PACKETS = 50
TOP_APP_PROTOS = 10
TOP_APP_PROTOS_OVERLAY = 5

# Reference-style colors (TCP / UDP)
PROTOCOL_COLORS: dict[str, str] = {
    "tcp": "#4DBBD5",
    "udp": "#E64B35",
    "icmp": "#00A087",
    "http": "#3C5488",
    "tls": "#F39B7F",
    "dns": "#8491B4",
    "control": "#E64B35",
    "data": "#4DBBD5",
    "other": "#7E6148",
    "unknown": "#7E6148",
}


def use_plot_style() -> None:
    """Seaborn-like whitegrid when available."""
    for style in ("seaborn-v0_8-whitegrid", "seaborn-whitegrid", "ggplot"):
        try:
            plt.style.use(style)
            return
        except OSError:
            continue


def positive(series: pd.Series) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy()
    return values[values > 0]


def save_figure(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def plot_empty_notice(
    *,
    out_path: Path,
    title: str,
    message: str = "No plottable values for this selection.",
) -> Path:
    """Write a placeholder figure when a chart has no data."""
    use_plot_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.axis("off")
    ax.set_title(title)
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=11, transform=ax.transAxes)
    save_figure(fig, out_path)
    plt.style.use("default")
    return out_path


def title_suffix(packets: pd.DataFrame) -> str:
    n = len(packets)
    if n == 0:
        return f"(n={n})"
    t0 = packets["time_epoch"].min()
    t1 = packets["time_epoch"].max()
    return f"(n={n:,}, span={t1 - t0:.3f}s)"


def compute_ccdf(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Complementary CDF: P(X >= x)."""
    x = np.sort(values)
    n = len(x)
    if n == 0:
        return x, x
    y = 1.0 - (np.arange(1, n + 1) / n)
    return x, y


def _color_for_label(label: str) -> str:
    key = str(label).lower()
    return PROTOCOL_COLORS.get(key, "#4C72B0")


def _cap_axis_max(value: float) -> float:
    """Round a percentile cap up to a readable axis limit."""
    if not np.isfinite(value) or value <= 0:
        return 1.0
    if value <= 1_000:
        return float(np.ceil(value / 100.0) * 100.0)
    if value <= 10_000:
        return float(np.ceil(value / 1_000.0) * 1_000.0)
    return float(np.ceil(value / 5_000.0) * 5_000.0)


def _format_byte_cap(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{int(value / 1_000)}k"
    return f"{int(value)}"


def plot_pdf_with_overflow_bin(
    values: np.ndarray,
    *,
    out_path: Path,
    xlabel: str,
    title: str,
    percentile_cap: float = 99.0,
    x_max: float | None = None,
    n_bins: int = 50,
    color: str = "#4C72B0",
    overflow_color: str = "#E64B35",
    log_y: bool = False,
) -> Path:
    """
    Linear-scale PDF with a shortened x-axis and one overflow bin for values above the cap.
    """
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data)]
    data = data[data > 0]
    if len(data) == 0:
        raise ValueError("No positive values to plot")

    if x_max is None:
        x_max = _cap_axis_max(float(np.percentile(data, percentile_cap)))
    else:
        x_max = float(x_max)

    if x_max <= 0:
        x_max = float(np.max(data))

    bin_edges = np.linspace(0.0, x_max, n_bins + 1)
    bin_width = x_max / n_bins
    in_range = data[data <= x_max]
    n_overflow = int(np.sum(data > x_max))
    n_total = len(data)

    counts, _ = np.histogram(in_range, bins=bin_edges)
    densities = counts / (n_total * bin_width)
    centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0

    use_plot_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.bar(
        centers,
        densities,
        width=bin_width * 0.95,
        align="center",
        color=color,
        alpha=0.75,
        edgecolor="white",
        linewidth=0.4,
        label=f"≤ {_format_byte_cap(x_max)} B",
    )

    overflow_center = x_max + bin_width / 2.0
    overflow_density = n_overflow / (n_total * bin_width) if n_overflow else 0.0
    if n_overflow:
        ax.bar(
            [overflow_center],
            [overflow_density],
            width=bin_width * 0.95,
            align="center",
            color=overflow_color,
            alpha=0.85,
            edgecolor="white",
            linewidth=0.4,
            label=f"> {_format_byte_cap(x_max)} B (n={n_overflow:,})",
        )

    ax.set_xlim(0.0, x_max + bin_width)
    if log_y:
        ax.set_yscale("log")
        ymin, ymax = ax.get_ylim()
        if ymin <= 0:
            ax.set_ylim(bottom=max(ymax * 1e-6, 1e-12), top=ymax)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Density")
    cap_note = f"cap={_format_byte_cap(x_max)} B"
    if n_overflow:
        ax.set_title(f"{title}\n[{cap_note}, {n_overflow:,} flows in overflow bin]")
    else:
        ax.set_title(f"{title}\n[{cap_note}]")
    if n_overflow:
        ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3, which="both" if log_y else "major")
    save_figure(fig, out_path)
    plt.style.use("default")
    return out_path


def plot_pdf(
    values: np.ndarray,
    *,
    out_path: Path,
    xlabel: str,
    title: str,
    log_x: bool = False,
    log_y: bool = False,
    bins: np.ndarray | int = HIST_BINS,
    color: str = "#4C72B0",
) -> Path:
    """Probability density function (normalized histogram, no KDE)."""
    use_plot_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.hist(
        values,
        bins=bins,
        density=True,
        color=color,
        alpha=0.75,
        edgecolor="white",
        linewidth=0.4,
    )
    if log_x:
        ax.set_xscale("log")
    if log_y:
        ax.set_yscale("log")
        ymin, ymax = ax.get_ylim()
        if ymin <= 0:
            ax.set_ylim(bottom=max(ymax * 1e-6, 1e-12), top=ymax)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Density")
    ax.set_title(title)
    ax.grid(True, alpha=0.3, which="both" if (log_x or log_y) else "major")
    save_figure(fig, out_path)
    plt.style.use("default")
    return out_path


def log_bins(values_list: list[np.ndarray], *, n_bins: int = 50) -> np.ndarray:
    """Shared log-spaced bin edges for positive values."""
    parts = [np.asarray(v, dtype=float) for v in values_list if len(v) > 0]
    if not parts:
        return np.logspace(-6, 3, n_bins + 1)
    combined = np.concatenate(parts)
    positive = combined[np.isfinite(combined) & (combined > 0)]
    if len(positive) == 0:
        return np.logspace(-6, 3, n_bins + 1)
    lo = max(float(np.min(positive)), 1e-12)
    hi = max(float(np.max(positive)), lo * 10)
    if hi <= lo:
        hi = lo * 10
    return np.logspace(np.log10(lo), np.log10(hi), n_bins + 1)


def plot_pdf_overlay(
    groups: dict[str, np.ndarray],
    *,
    out_path: Path,
    xlabel: str,
    title: str,
    bins: np.ndarray | int | None = None,
    legend_title: str = "protocol",
    log_x: bool = False,
    log_y: bool = False,
    n_bins: int = 50,
) -> Path:
    """
    Overlaid PDF histograms per group (density only, no KDE).

    Each group is normalized independently (seaborn common_norm=False).
    """
    use_plot_style()
    arrays = [v for v in groups.values() if len(v) > 0]
    if bins is None and log_x:
        bin_edges = log_bins(arrays, n_bins=n_bins)
    elif bins is None:
        bin_edges = HIST_BINS
    else:
        bin_edges = bins

    fig, ax = plt.subplots(figsize=FIGSIZE)
    for label, values in groups.items():
        if len(values) == 0:
            continue
        ax.hist(
            values,
            bins=bin_edges,
            density=True,
            alpha=0.55,
            label=label,
            color=_color_for_label(label),
            edgecolor="white",
            linewidth=0.3,
        )
    if log_x:
        ax.set_xscale("log")
    if log_y:
        ax.set_yscale("log")
        ymin, ymax = ax.get_ylim()
        if ymin <= 0:
            ax.set_ylim(bottom=max(ymax * 1e-6, 1e-12), top=ymax)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Density")
    ax.set_title(title)
    ax.legend(title=legend_title)
    ax.grid(True, alpha=0.3, which="both" if (log_x or log_y) else "major")
    save_figure(fig, out_path)
    plt.style.use("default")
    return out_path


def plot_ccdf_overlay(
    groups: dict[str, np.ndarray],
    *,
    out_path: Path,
    xlabel: str,
    title: str,
    legend_title: str = "protocol",
    log_x: bool = True,
) -> Path:
    """Overlaid CCDF curves per group."""
    use_plot_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    for label, values in groups.items():
        if len(values) == 0:
            continue
        x, y = compute_ccdf(values)
        ax.step(
            x,
            y,
            where="post",
            label=label,
            color=_color_for_label(label),
            linewidth=1.5,
        )
    if log_x:
        ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("P(X >= x)")
    ax.set_title(title)
    ax.legend(title=legend_title)
    ax.grid(True, alpha=0.3, which="both")
    ax.set_ylim(1e-6, 1.05)
    save_figure(fig, out_path)
    plt.style.use("default")
    return out_path


def plot_ccdf(
    values: np.ndarray,
    *,
    out_path: Path,
    xlabel: str,
    title: str,
    log_x: bool = True,
    color: str = "#2563eb",
) -> Path:
    x, y = compute_ccdf(values)
    use_plot_style()
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.step(x, y, where="post", color=color, linewidth=1.5)
    if log_x:
        ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("P(X >= x)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3, which="both")
    ax.set_ylim(bottom=max(1e-6, y.min() * 0.5) if len(y) else 1e-6, top=1.05)
    save_figure(fig, out_path)
    plt.style.use("default")
    return out_path
