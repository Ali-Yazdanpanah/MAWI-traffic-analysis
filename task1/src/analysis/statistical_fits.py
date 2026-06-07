#!/usr/bin/env python3
"""Fit parametric distributions to Task I features and write GoF summaries."""

from __future__ import annotations

import argparse
import json
import shutil
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

# Heavy-tailed flow metrics (size, duration, throughput) need pareto in the mix.
HEAVY_TAIL_CANDIDATES = ("lognormal", "pareto", "weibull", "gamma", "exponential")

_METRIC_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "iat",
        "label": "Inter-arrival time",
        "xlabel": "inter-arrival time (s)",
        "source": "packets",
        "column": "time_delta",
        "log_x": True,
        "log_y": True,
        "candidates": ("poisson", "exponential", "lognormal", "weibull", "gamma"),
        # Poisson arrivals are the reference model for IAT; always headline it
        # even when a heavier-tailed law scores a marginally lower AIC.
        "primary_fit": "poisson",
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
        "candidates": HEAVY_TAIL_CANDIDATES,
    },
    {
        "id": "flow_byte_sum",
        "label": "Flow size",
        "xlabel": "flow size (bytes)",
        "source": "flows",
        "column": "byte_sum",
        "log_x": True,
        "log_y": True,
        "candidates": HEAVY_TAIL_CANDIDATES,
    },
    {
        "id": "flow_throughput",
        "label": "Flow throughput",
        "xlabel": "throughput (bit/s)",
        "source": "flows",
        "column": "throughput_bps",
        "log_x": True,
        "log_y": True,
        "candidates": HEAVY_TAIL_CANDIDATES,
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

    # Headline the configured primary distribution when present (e.g. Poisson for
    # IAT); otherwise fall back to the lowest-AIC candidate.
    chosen = comparison.iloc[0]
    fit_kind = "best"
    primary = metric.get("primary_fit")
    if primary:
        match = comparison[comparison["distribution"] == primary]
        if not match.empty:
            chosen = match.iloc[0]
            fit_kind = primary

    fit = fit_result_from_row(chosen, dataset=dataset_id)
    row = fit.to_dict()
    row["label"] = metric["label"]
    row["caption"] = fit_summary_caption(fit)

    fit_word = fit.distribution if fit_kind != "best" else "best fit"
    base_title = f"{metric['label']} PDF + {fit_word} {title_suffix_text}"

    # Emit the PDF+fit at the configured "primary" scale (kept as `_pdf_fit.png`
    # for the notebook / segment copies) plus semi-log (log-x, linear-y) and
    # linear (linear-x, linear-y) variants. Linear/semi-log expose bulk-region
    # misfit that log-log hides; together they let the reader judge GoF by eye.
    _SCALE_TAGS = {
        (True, True): "log-log",
        (True, False): "semi-log (log-x)",
        (False, False): "linear",
        (False, True): "linear-x, log-y",
    }
    pdf_variants = (
        ("", bool(metric["log_x"]), bool(metric["log_y"])),  # primary scale
        ("_semilog", True, False),
        ("_linear", False, False),
    )
    seen_scales: set[tuple[bool, bool]] = set()
    for suffix, log_x, log_y in pdf_variants:
        scale_key = (log_x, log_y)
        if suffix and scale_key in seen_scales:
            continue  # skip a variant that duplicates the primary scale
        seen_scales.add(scale_key)
        variant_path = plots_dir / f"{dataset_id}_pdf_fit{suffix}.png"
        plot_pdf_with_fit(
            positive_values,
            fit,
            out_path=variant_path,
            xlabel=metric["xlabel"],
            title=f"{base_title} [{_SCALE_TAGS[scale_key]}]",
            log_x=log_x,
            log_y=log_y,
        )
        paths.append(variant_path)

    qq_path = plots_dir / f"{dataset_id}_qq.png"
    plot_qq(
        positive_values,
        fit,
        out_path=qq_path,
        title=f"{metric['label']} Q–Q ({fit.distribution}) {title_suffix_text}",
    )
    paths.append(qq_path)
    return paths, row


def _attach_overall_fits_to_segment(
    breakdown: dict[str, Any],
    *,
    overall_by_metric: dict[str, dict[str, Any]],
    root_tables_dir: Path,
    root_plots_dir: Path,
    segment_tables: Path,
    segment_plots: Path,
) -> tuple[list[Path], list[dict[str, Any]]]:
    """Copy aggregate fits into a segment folder for side-by-side comparison."""
    paths: list[Path] = []
    rows: list[dict[str, Any]] = []
    segment_id = breakdown["id"]
    metric_ids = tuple(breakdown["packet_metrics"]) + tuple(breakdown["flow_metrics"])

    for metric_id in metric_ids:
        overall_row = overall_by_metric.get(metric_id)
        if overall_row is None:
            continue

        dataset_id = f"{metric_id}__all"
        row = dict(overall_row)
        row["dataset"] = dataset_id
        row["segment"] = segment_id
        row["segment_label"] = breakdown["label"]
        row["group"] = "all"
        rows.append(row)

        candidates_src = root_tables_dir / f"{metric_id}_candidates.csv"
        if candidates_src.is_file():
            candidates_dst = segment_tables / f"{dataset_id}_candidates.csv"
            shutil.copy2(candidates_src, candidates_dst)
            paths.append(candidates_dst)

        for suffix in (
            "_pdf_fit.png",
            "_pdf_fit_semilog.png",
            "_pdf_fit_linear.png",
            "_qq.png",
        ):
            src = root_plots_dir / f"{metric_id}{suffix}"
            if not src.is_file():
                continue
            dst = segment_plots / f"{dataset_id}{suffix}"
            shutil.copy2(src, dst)
            paths.append(dst)

    return paths, rows


def _run_breakdown_fits(
    breakdown: dict[str, Any],
    packets: pd.DataFrame,
    flows: pd.DataFrame,
    *,
    tables_dir: Path,
    plots_dir: Path,
    overall_by_metric: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[Path], list[dict[str, Any]]]:
    paths: list[Path] = []
    rows: list[dict[str, Any]] = []
    segment_id = breakdown["id"]
    segment_tables = tables_dir / "by_segment" / segment_id
    segment_plots = plots_dir / "by_segment" / segment_id
    segment_tables.mkdir(parents=True, exist_ok=True)
    segment_plots.mkdir(parents=True, exist_ok=True)

    if overall_by_metric:
        overall_paths, overall_rows = _attach_overall_fits_to_segment(
            breakdown,
            overall_by_metric=overall_by_metric,
            root_tables_dir=tables_dir,
            root_plots_dir=plots_dir,
            segment_tables=segment_tables,
            segment_plots=segment_plots,
        )
        paths.extend(overall_paths)
        rows.extend(overall_rows)

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
    overall_by_metric: dict[str, dict[str, Any]] = {}

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
        overall_by_metric[metric["id"]] = row
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
            overall_by_metric=overall_by_metric,
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

        print("\nSegmented fits (overall + groups per breakdown):")
        segmented = summary[summary["segment"] != "all"]
        for segment_id in segmented["segment"].drop_duplicates():
            print(f"  [{segment_id}]")
            part = segmented[segmented["segment"] == segment_id]
            for _, row in part.sort_values(["dataset", "group"]).iterrows():
                print(
                    f"    {row['dataset']} / {row['group']}: "
                    f"{row['distribution']} (KS p={row['ks_pvalue']:.2e}, AIC={row['aic']:.1f})"
                )
    print(f"\nWrote {len(paths)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
