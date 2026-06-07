#!/usr/bin/env python3
"""Entry point: all packet- and flow-level plots."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from analysis.bootstrap import load_packets  # noqa: E402
from analysis.flow.plot import plot_all as plot_flow  # noqa: E402
from analysis.packet.plot import plot_all as plot_packet  # noqa: E402
from analysis.timeseries.plot import plot_all as plot_timeseries  # noqa: E402
from analysis.results_paths import (  # noqa: E402
    FLOW_DISTRIBUTION,
    FLOW_FEATURES,
    PACKET_DISTRIBUTION,
    PACKET_FEATURES,
    RESULTS_ROOT,
    TIMESERIES_DISTRIBUTION,
    TIMESERIES_FEATURES,
    resolve_results_dir,
    resolve_statistical_fits_dir,
    resolve_statistical_fits_plots_dir,
)
from analysis.statistical_fits import fit_all as run_statistical_fits  # noqa: E402


def plot_all(
    packets=None,
    *,
    jsonl: str | Path | None = None,
    limit: int | None = None,
    results_root: str | Path | None = None,
    run_fits: bool = True,
) -> list[Path]:
    if packets is None:
        packets = load_packets(jsonl, limit=limit)
    paths: list[Path] = []
    paths.extend(plot_packet(packets, results_root=results_root))
    paths.extend(plot_flow(packets, results_root=results_root))
    paths.extend(plot_timeseries(packets, results_root=results_root))
    if run_fits:
        fit_paths, _ = run_statistical_fits(packets, results_root=results_root)
        paths.extend(fit_paths)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plot all Task I figures from MAWI JSONL.")
    parser.add_argument("jsonl", nargs="?", default=None)
    parser.add_argument("-n", "--limit", type=int, default=None)
    parser.add_argument("-o", "--results-root", default=str(RESULTS_ROOT))
    parser.add_argument("--no-fits", action="store_true", help="Skip distribution fitting.")
    args = parser.parse_args(argv)

    packets = load_packets(args.jsonl, limit=args.limit)
    paths = plot_all(packets, results_root=args.results_root, run_fits=not args.no_fits)
    n = len(packets)
    print(f"Processed n={n:,} packets")
    print(f"  packet/features:     {resolve_results_dir(n, category=PACKET_FEATURES, results_root=args.results_root)}")
    print(f"  packet/distribution: {resolve_results_dir(n, category=PACKET_DISTRIBUTION, results_root=args.results_root)}")
    print(f"  flow/features:       {resolve_results_dir(n, category=FLOW_FEATURES, results_root=args.results_root)}")
    print(f"  flow/distribution:   {resolve_results_dir(n, category=FLOW_DISTRIBUTION, results_root=args.results_root)}")
    print(f"  timeseries/features: {resolve_results_dir(n, category=TIMESERIES_FEATURES, results_root=args.results_root)}")
    if not args.no_fits:
        print(f"  statistical-fits:    {resolve_statistical_fits_dir(n, results_root=args.results_root)}")
        print(f"  fit plots:           {resolve_statistical_fits_plots_dir(n, results_root=args.results_root)}")
    print(f"Wrote {len(paths)} plots:")
    for path in paths:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
