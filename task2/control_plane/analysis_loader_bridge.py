"""Wire Task I analysis modules to Task II capture loaders."""

from __future__ import annotations

from repo_paths import ensure_task1_on_path

ensure_task1_on_path()

import analysis.bootstrap as task1_bootstrap
import analysis.flow.distributions as flow_distributions
import analysis.flow.features as flow_features
import analysis.packet.distributions as packet_distributions
import analysis.packet.features as packet_features
import analysis.statistical_fits as statistical_fits
import analysis.timeseries.features as timeseries_features

import capture_jsonl_loader as task2_bootstrap

_PATCHED = False


def patch_task1_loaders() -> None:
    """Point every Task I loader import at the Task II capture JSONL loader."""
    global _PATCHED
    if _PATCHED:
        return

    load_packets = task2_bootstrap.load_packets
    load_flows = task2_bootstrap.load_flows

    for module in (
        task1_bootstrap,
        statistical_fits,
        flow_features,
        flow_distributions,
        packet_features,
        packet_distributions,
        timeseries_features,
    ):
        module.load_packets = load_packets  # type: ignore[attr-defined]
        if hasattr(module, "load_flows"):
            module.load_flows = load_flows  # type: ignore[attr-defined]

    _PATCHED = True
