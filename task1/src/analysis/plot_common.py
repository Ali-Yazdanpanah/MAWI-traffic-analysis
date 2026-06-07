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
    parts = [v for v in values_list if len(v) > 0]
    if not parts:
        return np.logspace(0, 3, n_bins + 1)
    combined = np.concatenate(parts)
    lo = max(float(np.min(combined)), 1.0)
    hi = max(float(np.max(combined)), lo * 10)
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
) -> Path:
    x, y = compute_ccdf(values)
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.step(x, y, where="post", color="#2563eb", linewidth=1.5)
    if log_x:
        ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("P(X >= x)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3, which="both")
    ax.set_ylim(bottom=max(1e-6, y.min() * 0.5) if len(y) else 1e-6, top=1.05)
    save_figure(fig, out_path)
    return out_path
