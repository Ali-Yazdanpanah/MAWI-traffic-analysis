#!/usr/bin/env python3
"""Fit parametric distributions to Task I features and write GoF summaries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from analysis.bootstrap import load_flows, load_packets  # noqa: E402
from analysis.distribution_fitting import (  # noqa: E402
    DEFAULT_CANDIDATES,
    compare_candidates,
    fit_result_from_row,
    fit_summary_caption,
    plot_pdf_with_fit,
    plot_qq,
)
from analysis.plot_common import MIN_GROUP_PACKETS, positive, title_suffix  # noqa: E402
from analysis.results_paths import (  # noqa: E402
    RESULTS_ROOT,
    resolve_statistical_fits_dir,
    resolve_statistical_fits_plots_dir,
)

MIN_FIT_SAMPLES = max(MIN_GROUP_PACKETS, 10)

_METRIC_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "iat",
        "label": "Inter-arrival time",
        "xlabel": "inter-arrival time (s)",
        "source": "packets",
        "column": "time_delta",
        "log_x": True,
        "log_y": True,
        "candidates": ("exponential", "lognormal", "weibull", "gamma"),
    },
    {
        "id": "frame_len",
        "label": "Packet size",
        "xlabel": "frame length (bytes)",
        "source": "packets",
        "column": "frame_len",
        "log_x": False,
        "log_y": False,
        "candidates": DEFAULT_CANDIDATES,
    },
    {
        "id": "flow_duration",
        "label": "Flow duration",
        "xlabel": "flow duration (s)",
        "source": "flows",
        "column": "duration",
        "log_x": True,
        "log_y": True,
        "candidates": DEFAULT_CANDIDATES,
    },
    {
        "id": "flow_byte_sum",
        "label": "Flow size",
        "xlabel": "flow size (bytes)",
        "source": "flows",
        "column": "byte_sum",
        "log_x": True,
        "log_y": True,
        "candidates": DEFAULT_CANDIDATES,
    },
    {
        "id": "flow_throughput",
        "label": "Flow throughput",
        "xlabel": "throughput (bit/s)",
        "source": "flows",
        "column": "throughput_bps",
        "log_x": True,
        "log_y": True,
        "candidates": DEFAULT_CANDIDATES,
    },
)

_METRICS_BY_ID = {spec["id"]: spec for spec in _METRIC_SPECS}

_BREAKDOWN_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "transport_proto",
        "label": "Transport protocol",
        "packet_column": "transport_proto",
        "flow_column": "transport_proto",
        "groups": ("tcp", "udp"),
        "packet_metrics": ("iat", "frame_len"),
        "flow_metrics": ("flow_duration", "flow_byte_sum", "flow_throughput"),
    },
    {
        "id": "packet_role",
        "label": "Control vs data",
        "packet_column": "packet_role",
        "flow_column": None,
        "groups": ("control", "data"),
        "packet_metrics": ("iat", "frame_len"),
        "flow_metrics": (),
    },
    {
        "id": "flow_size_class",
        "label": "Mice vs elephant flows",
        "packet_column": None,
        "flow_column": "flow_size_class",
        "groups": ("mice", "elephant"),
        "packet_metrics": (),
        "flow_metrics": ("flow_duration", "flow_byte_sum", "flow_throughput"),
    },
    {
        "id": "app_proto",
        "label": "Application protocol",
        "packet_column": "app_proto",
        "flow_column": "app_proto",
        "groups": "top",
        "packet_metrics": ("iat", "frame_len"),
        "flow_metrics": ("flow_duration", "flow_byte_sum"),
        "top_n": 5,
    },
)


def _series_for_metric(
    spec: dict[str, Any],
    packets: pd.DataFrame,
    flows: pd.DataFrame,
) -> pd.Series:
    if spec["source"] == "packets":
        return packets[spec["column"]]
    return flows[spec["column"]]


def _normalize_label(value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "unknown"
    return str(value).strip().lower()


def _top_groups(series: pd.Series, *, top_n: int, min_count: int) -> list[str]:
    labels = series.map(_normalize_label)
    counts = labels.value_counts()
    counts = counts[counts.index != "unknown"]
    keep = counts[counts >= min_count].head(top_n).index.tolist()
    return [str(label) for label in keep]


def _groups_for_breakdown(
    breakdown: dict[str, Any],
    packets: pd.DataFrame,
    flows: pd.DataFrame,
    *,
    source: str,
) -> list[str]:
    configured = breakdown["groups"]
    if configured != "top":
        return [str(group) for group in configured]

    top_n = int(breakdown.get("top_n", 5))
    if source == "packets":
        column = breakdown["packet_column"]
        if not column:
            return []
        return _top_groups(packets[column], top_n=top_n, min_count=MIN_FIT_SAMPLES)
    column = breakdown["flow_column"]
    if not column:
        return []
    return _top_groups(flows[column], top_n=top_n, min_count=MIN_FIT_SAMPLES)


def _filter_frame(
    frame: pd.DataFrame,
    column: str,
    group: str,
) -> pd.DataFrame:
    labels = frame[column].map(_normalize_label)
    return frame.loc[labels == group]


def _fit_metric(
    values: np.ndarray,
    metric: dict[str, Any],
    *,
    dataset_id: str,
    tables_dir: Path,
    plots_dir: Path,
    title_suffix_text: str,
    write_candidates: bool = True,
) -> tuple[list[Path], dict[str, Any] | None]:
    positive_values = positive(pd.Series(values))
    if len(positive_values) < MIN_FIT_SAMPLES:
        return [], None

    comparison = compare_candidates(
        positive_values,
        dataset=dataset_id,
        candidates=tuple(metric["candidates"]),
    )
    if comparison.empty:
        return [], None

    paths: list[Path] = []
    if write_candidates:
        csv_path = tables_dir / f"{dataset_id}_candidates.csv"
        comparison.to_csv(csv_path, index=False)
        paths.append(csv_path)

    best = comparison.iloc[0]
    fit = fit_result_from_row(best, dataset=dataset_id)
    row = fit.to_dict()
    row["label"] = metric["label"]
    row["caption"] = fit_summary_caption(fit)

    pdf_path = plots_dir / f"{dataset_id}_pdf_fit.png"
    plot_pdf_with_fit(
        positive_values,
        fit,
        out_path=pdf_path,
        xlabel=metric["xlabel"],
        title=f"{metric['label']} PDF + best fit {title_suffix_text}",
        log_x=metric["log_x"],
        log_y=metric["log_y"],
    )
    paths.append(pdf_path)

    qq_path = plots_dir / f"{dataset_id}_qq.png"
    plot_qq(
        positive_values,
        fit,
        out_path=qq_path,
        title=f"{metric['label']} Q–Q ({fit.distribution}) {title_suffix_text}",
    )
    paths.append(qq_path)
    return paths, row


def _run_breakdown_fits(
    breakdown: dict[str, Any],
    packets: pd.DataFrame,
    flows: pd.DataFrame,
    *,
    tables_dir: Path,
    plots_dir: Path,
) -> tuple[list[Path], list[dict[str, Any]]]:
    paths: list[Path] = []
    rows: list[dict[str, Any]] = []
    segment_id = breakdown["id"]
    segment_tables = tables_dir / "by_segment" / segment_id
    segment_plots = plots_dir / "by_segment" / segment_id
    segment_tables.mkdir(parents=True, exist_ok=True)
    segment_plots.mkdir(parents=True, exist_ok=True)

    for metric_id in breakdown["packet_metrics"]:
        metric = _METRICS_BY_ID[metric_id]
        column = breakdown["packet_column"]
        if not column:
            continue
        groups = _groups_for_breakdown(breakdown, packets, flows, source="packets")
        for group in groups:
            subset = _filter_frame(packets, column, group)
            dataset_id = f"{metric_id}__{group}"
            suffix = f"({group}, n={len(subset):,})"
            metric_paths, row = _fit_metric(
                _series_for_metric(metric, subset, flows).to_numpy(),
                metric,
                dataset_id=dataset_id,
                tables_dir=segment_tables,
                plots_dir=segment_plots,
                title_suffix_text=suffix,
            )
            if row is None:
                continue
            row["segment"] = segment_id
            row["segment_label"] = breakdown["label"]
            row["group"] = group
            rows.append(row)
            paths.extend(metric_paths)

    for metric_id in breakdown["flow_metrics"]:
        metric = _METRICS_BY_ID[metric_id]
        column = breakdown["flow_column"]
        if not column:
            continue
        groups = _groups_for_breakdown(breakdown, packets, flows, source="flows")
        for group in groups:
            subset = _filter_frame(flows, column, group)
            dataset_id = f"{metric_id}__{group}"
            suffix = f"({group}, n={len(subset):,})"
            metric_paths, row = _fit_metric(
                _series_for_metric(metric, packets, subset).to_numpy(),
                metric,
                dataset_id=dataset_id,
                tables_dir=segment_tables,
                plots_dir=segment_plots,
                title_suffix_text=suffix,
            )
            if row is None:
                continue
            row["segment"] = segment_id
            row["segment_label"] = breakdown["label"]
            row["group"] = group
            rows.append(row)
            paths.extend(metric_paths)

    if rows:
        segment_summary = pd.DataFrame(rows)
        summary_path = segment_tables / "best_fits_summary.csv"
        segment_summary.to_csv(summary_path, index=False)
        paths.append(summary_path)

    return paths, rows


def fit_all(
    packets: pd.DataFrame | None = None,
    flows: pd.DataFrame | None = None,
    *,
    jsonl: str | Path | None = None,
    limit: int | None = None,
    results_root: str | Path | None = None,
) -> tuple[list[Path], pd.DataFrame]:
    if packets is None:
        packets = load_packets(jsonl, limit=limit)
    if flows is None:
        flows = load_flows(packets)
    if packets.empty:
        raise ValueError("No packets to fit")

    n = len(packets)
    tables_dir = resolve_statistical_fits_dir(n, results_root=results_root)
    plots_dir = resolve_statistical_fits_plots_dir(n, results_root=results_root)
    tables_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict[str, Any]] = []
    paths: list[Path] = []

    for metric in _METRIC_SPECS:
        suffix = title_suffix(packets) if metric["source"] == "packets" else f"(flows={len(flows):,})"
        metric_paths, row = _fit_metric(
            _series_for_metric(metric, packets, flows).to_numpy(),
            metric,
            dataset_id=metric["id"],
            tables_dir=tables_dir,
            plots_dir=plots_dir,
            title_suffix_text=suffix,
        )
        if row is None:
            continue
        row["segment"] = "all"
        row["segment_label"] = "All traffic"
        row["group"] = "all"
        all_rows.append(row)
        paths.extend(metric_paths)

    segmented_rows: list[dict[str, Any]] = []
    for breakdown in _BREAKDOWN_SPECS:
        segment_paths, segment_rows = _run_breakdown_fits(
            breakdown,
            packets,
            flows,
            tables_dir=tables_dir,
            plots_dir=plots_dir,
        )
        paths.extend(segment_paths)
        segmented_rows.extend(segment_rows)

    all_rows.extend(segmented_rows)
    summary = pd.DataFrame(all_rows)
    if not summary.empty:
        summary_path = tables_dir / "best_fits_summary.csv"
        summary.to_csv(summary_path, index=False)
        paths.append(summary_path)

        json_path = tables_dir / "best_fits_summary.json"
        json_path.write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
        paths.append(json_path)

    return paths, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fit distributions to Task I features and report goodness-of-fit.",
    )
    parser.add_argument("jsonl", nargs="?", default=None)
    parser.add_argument("-n", "--limit", type=int, default=None)
    parser.add_argument("-o", "--results-root", default=str(RESULTS_ROOT))
    args = parser.parse_args(argv)

    packets = load_packets(args.jsonl, limit=args.limit)
    paths, summary = fit_all(packets, results_root=args.results_root)
    n = len(packets)

    print(f"Processed n={n:,} packets")
    print(f"  tables: {resolve_statistical_fits_dir(n, results_root=args.results_root)}")
    print(f"  plots:  {resolve_statistical_fits_plots_dir(n, results_root=args.results_root)}")
    if not summary.empty:
        print("\nAggregate best fits (lowest AIC):")
        aggregate = summary[summary["segment"] == "all"]
        for _, row in aggregate.iterrows():
            print(f"  {row['dataset']}: {row['distribution']} (KS p={row['ks_pvalue']:.2e}, AIC={row['aic']:.1f})")

        print("\nSegmented fits:")
        segmented = summary[summary["segment"] != "all"]
        for segment_id in segmented["segment"].drop_duplicates():
            print(f"  [{segment_id}]")
            part = segmented[segmented["segment"] == segment_id]
            for _, row in part.iterrows():
                print(
                    f"    {row['dataset']} / {row['group']}: "
                    f"{row['distribution']} (KS p={row['ks_pvalue']:.2e}, AIC={row['aic']:.1f})"
                )
    print(f"\nWrote {len(paths)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
