#!/usr/bin/env python3
"""Entry point: flow-level plots (features + distributions)."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from analysis.flow import distributions, features  # noqa: E402
from analysis.plot_cli import main_level, plot_all_level  # noqa: E402
from analysis.results_paths import FLOW_DISTRIBUTION, FLOW_FEATURES  # noqa: E402


def plot_all(packets=None, *, jsonl=None, limit=None, results_root=None, features_only=False, distributions_only=False):
    from analysis.bootstrap import load_packets

    if packets is None:
        packets = load_packets(jsonl, limit=limit)
    return plot_all_level(
        packets,
        features_mod=features,
        distributions_mod=distributions,
        results_root=results_root,
        features_only=features_only,
        distributions_only=distributions_only,
    )


def main(argv=None) -> int:
    return main_level(
        "flow",
        features_category=FLOW_FEATURES,
        distribution_category=FLOW_DISTRIBUTION,
        features_mod=features,
        distributions_mod=distributions,
        description="Plot flow-level figures from MAWI JSONL.",
        argv=argv,
    )


if __name__ == "__main__":
    sys.exit(main())
