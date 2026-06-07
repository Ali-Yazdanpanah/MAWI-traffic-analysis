"""Shared CLI and orchestration for packet- and flow-level plot modules."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from analysis.bootstrap import default_jsonl_path, load_packets
from analysis.results_paths import RESULTS_ROOT, resolve_results_dir


def plot_all_level(
    packets,
    *,
    features_mod: Any,
    distributions_mod: Any,
    results_root: str | Path | None = None,
    features_only: bool = False,
    distributions_only: bool = False,
) -> list[Path]:
    paths: list[Path] = []
    if not distributions_only:
        paths.extend(features_mod.plot_all(packets, results_root=results_root))
    if not features_only:
        paths.extend(distributions_mod.plot_all(packets, results_root=results_root))
    return paths


def main_level(
    level: str,
    *,
    features_category: str,
    distribution_category: str,
    features_mod: Any,
    distributions_mod: Any,
    description: str,
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "jsonl",
        nargs="?",
        default=None,
        help=f"JSONL (default: {default_jsonl_path()})",
    )
    parser.add_argument("-n", "--limit", type=int, default=None)
    parser.add_argument("-o", "--results-root", default=str(RESULTS_ROOT))
    parser.add_argument("--features-only", action="store_true")
    parser.add_argument("--distributions-only", action="store_true")
    args = parser.parse_args(argv)

    packets = load_packets(args.jsonl, limit=args.limit)
    paths = plot_all_level(
        packets,
        features_mod=features_mod,
        distributions_mod=distributions_mod,
        results_root=args.results_root,
        features_only=args.features_only,
        distributions_only=args.distributions_only,
    )
    n = len(packets)
    print(f"[{level}] processed n={n:,} packets")
    print(f"  features:      {resolve_results_dir(n, category=features_category, results_root=args.results_root)}")
    print(f"  distribution:  {resolve_results_dir(n, category=distribution_category, results_root=args.results_root)}")
    print(f"Wrote {len(paths)} {level} plots:")
    for path in paths:
        print(f"  {path}")
    return 0
