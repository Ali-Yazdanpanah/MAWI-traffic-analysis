"""Result directory layout keyed by number of packets processed."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _repo_root() -> Path:
    docker_repo = Path("/repo")
    if (docker_repo / "task1" / "src" / "analysis").is_dir():
        return docker_repo
    if (_REPO_ROOT / "task1" / "src" / "analysis").is_dir():
        return _REPO_ROOT
    return _REPO_ROOT


RESULTS_ROOT = _repo_root() / "task1" / "results"

# Under task1/results/n_<count>/plots/
PACKET_FEATURES = "packet/features"
PACKET_DISTRIBUTION = "packet/distribution"
FLOW_FEATURES = "flow/features"
FLOW_DISTRIBUTION = "flow/distribution"
TIMESERIES_FEATURES = "timeseries/features"
TIMESERIES_DISTRIBUTION = "timeseries/distribution"
STATISTICAL_FITS = "statistical-fits"


def resolve_results_dir(
    packet_count: int,
    *,
    category: str = PACKET_FEATURES,
    results_root: Path | str | None = None,
) -> Path:
    """
    Directory for outputs from a given packet sample size.

    Layout: <results_root>/n_<count>/plots/<category>/
    Examples:
      task1/results/n_100000/plots/packet/features/
      task1/results/n_100000/plots/packet/distribution/
    """
    root = Path(results_root) if results_root is not None else RESULTS_ROOT
    return root / f"n_{packet_count}" / "plots" / category


def resolve_statistical_fits_dir(
    packet_count: int,
    *,
    results_root: Path | str | None = None,
) -> Path:
    """Tables and JSON summaries: task1/results/n_<count>/statistical-fits/"""
    root = Path(results_root) if results_root is not None else RESULTS_ROOT
    return root / f"n_{packet_count}" / "statistical-fits"


def resolve_statistical_fits_plots_dir(
    packet_count: int,
    *,
    results_root: Path | str | None = None,
) -> Path:
    """Fit overlay and Q-Q plots: task1/results/n_<count>/plots/statistical-fits/"""
    return resolve_results_dir(
        packet_count,
        category=STATISTICAL_FITS,
        results_root=results_root,
    )
