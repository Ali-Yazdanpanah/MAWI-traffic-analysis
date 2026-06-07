#!/usr/bin/env python3
"""Plot Task II captures using the Task I analysis pipeline (identical chart set)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repo_paths import ensure_task1_on_path, task2_root

_TASK2_ROOT = task2_root()
ensure_task1_on_path()
_CONTROL_PLANE = Path(__file__).resolve().parent

if str(_CONTROL_PLANE) not in sys.path:
    sys.path.insert(0, str(_CONTROL_PLANE))

from analysis_loader_bridge import patch_task1_loaders  # noqa: E402

patch_task1_loaders()

import capture_jsonl_loader as task2_bootstrap  # noqa: E402
from analysis.plot_analysis import plot_all as task1_plot_all  # noqa: E402
from results_paths import (  # noqa: E402
    FLOW_DISTRIBUTION,
    FLOW_FEATURES,
    PACKET_DISTRIBUTION,
    PACKET_FEATURES,
    RESULTS_ROOT,
    TIMESERIES_FEATURES,
    resolve_results_dir,
    resolve_statistical_fits_dir,
    resolve_statistical_fits_plots_dir,
)


def plot_all(
    packets=None,
    *,
    jsonl: str | Path | None = None,
    limit: int | None = None,
    results_root: str | Path | None = None,
    run_fits: bool = True,
) -> list[Path]:
    """Run the same plot + fit pipeline as Task I ``plot_analysis.plot_all``."""
    if packets is None:
        packets = task2_bootstrap.load_packets(jsonl, limit=limit)
    return task1_plot_all(
        packets,
        results_root=results_root,
        run_fits=run_fits,
    )


def main(argv: list[str] | None = None) -> int:
    default_capture = task2_bootstrap.default_capture_path()
    parser = argparse.ArgumentParser(
        description="Plot Task II figures from capture JSONL (same charts as Task I)."
    )
    parser.add_argument(
        "jsonl",
        nargs="?",
        default=None,
        help=f"Capture JSONL (default: {default_capture})",
    )
    parser.add_argument("-n", "--limit", type=int, default=None)
    parser.add_argument("-o", "--results-root", default=str(RESULTS_ROOT))
    parser.add_argument("--no-fits", action="store_true", help="Skip distribution fitting.")
    args = parser.parse_args(argv)

    packets = task2_bootstrap.load_packets(args.jsonl, limit=args.limit)
    paths = plot_all(packets, results_root=args.results_root, run_fits=not args.no_fits)
    n = len(packets)
    print(f"[task2] processed n={n:,} packets (Task I chart set)")
    print(f"  packet/features:     {resolve_results_dir(n, category=PACKET_FEATURES, results_root=args.results_root)}")
    print(f"  packet/distribution: {resolve_results_dir(n, category=PACKET_DISTRIBUTION, results_root=args.results_root)}")
    print(f"  flow/features:       {resolve_results_dir(n, category=FLOW_FEATURES, results_root=args.results_root)}")
    print(f"  flow/distribution:   {resolve_results_dir(n, category=FLOW_DISTRIBUTION, results_root=args.results_root)}")
    print(f"  timeseries/features: {resolve_results_dir(n, category=TIMESERIES_FEATURES, results_root=args.results_root)}")
    if not args.no_fits:
        print(f"  statistical-fits:    {resolve_statistical_fits_dir(n, results_root=args.results_root)}")
        print(f"  fit plots:           {resolve_statistical_fits_plots_dir(n, results_root=args.results_root)}")
    print(f"Wrote {len(paths)} outputs:")
    for path in paths:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
