"""Task II results layout — reuses Task I path helpers with task2/results root."""

from __future__ import annotations

from pathlib import Path

from paths import ensure_task1_on_path, task2_root

ensure_task1_on_path()

from analysis.results_paths import (  # noqa: E402
    FLOW_DISTRIBUTION,
    FLOW_FEATURES,
    PACKET_DISTRIBUTION,
    PACKET_FEATURES,
    STATISTICAL_FITS,
    TIMESERIES_DISTRIBUTION,
    TIMESERIES_FEATURES,
    resolve_results_dir,
    resolve_statistical_fits_dir,
    resolve_statistical_fits_plots_dir,
)

RESULTS_ROOT: Path = task2_root() / "results"

__all__ = [
    "RESULTS_ROOT",
    "PACKET_FEATURES",
    "PACKET_DISTRIBUTION",
    "FLOW_FEATURES",
    "FLOW_DISTRIBUTION",
    "TIMESERIES_FEATURES",
    "TIMESERIES_DISTRIBUTION",
    "STATISTICAL_FITS",
    "resolve_results_dir",
    "resolve_statistical_fits_dir",
    "resolve_statistical_fits_plots_dir",
]
