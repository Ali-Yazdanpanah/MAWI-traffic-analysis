"""Wire Task I analysis modules to Task II capture loaders."""

from __future__ import annotations

from paths import ensure_task1_on_path

ensure_task1_on_path()

import analysis.bootstrap as task1_bootstrap
import analysis.flow.distributions as flow_distributions
import analysis.flow.features as flow_features
import analysis.statistical_fits as statistical_fits

import bootstrap as task2_bootstrap


def patch_task1_loaders() -> None:
    """Point Task I loaders at Task II bootstrap (P4 flow_id, telemetry JSONL)."""
    task1_bootstrap.load_flows = task2_bootstrap.load_flows
    task1_bootstrap.load_packets = task2_bootstrap.load_packets
    statistical_fits.load_flows = task2_bootstrap.load_flows
    statistical_fits.load_packets = task2_bootstrap.load_packets
    flow_features.load_flows = task2_bootstrap.load_flows
    flow_distributions.load_flows = task2_bootstrap.load_flows
