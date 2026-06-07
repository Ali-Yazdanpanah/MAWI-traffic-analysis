"""Load MAWI JSONL exports and generate Task I plots."""

from .bootstrap import (
    default_jsonl_path,
    load_flows,
    load_packets,
    load_raw_packets,
    summarize,
)
from .flow.plot import plot_all as plot_flow
from .packet.plot import plot_all as plot_packet
from .timeseries.link_utilization import plot_link_utilization
from .timeseries.plot import plot_all as plot_timeseries
from .results_paths import (
    FLOW_DISTRIBUTION,
    FLOW_FEATURES,
    PACKET_DISTRIBUTION,
    PACKET_FEATURES,
    RESULTS_ROOT,
    TIMESERIES_DISTRIBUTION,
    TIMESERIES_FEATURES,
    resolve_results_dir,
)


def plot_all_figures(*args, **kwargs):
    """Generate all packet- and flow-level plots."""
    from .plot_analysis import plot_all

    return plot_all(*args, **kwargs)


__all__ = [
    "default_jsonl_path",
    "load_flows",
    "load_packets",
    "load_raw_packets",
    "plot_all_figures",
    "plot_flow",
    "plot_packet",
    "plot_timeseries",
    "plot_link_utilization",
    "TIMESERIES_FEATURES",
    "TIMESERIES_DISTRIBUTION",
    "FLOW_DISTRIBUTION",
    "FLOW_FEATURES",
    "PACKET_DISTRIBUTION",
    "PACKET_FEATURES",
    "resolve_results_dir",
    "RESULTS_ROOT",
    "summarize",
]
