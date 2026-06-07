#!/usr/bin/env python3
"""End-to-end Task II pipeline: capture telemetry -> plot like Task I."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_CONTROL_PLANE = Path(__file__).resolve().parent
if str(_CONTROL_PLANE) not in sys.path:
    sys.path.insert(0, str(_CONTROL_PLANE))

from bmv2_thrift import read_active_flows as read_active_flows_thrift
from bmv2_thrift import read_global_state as read_global_state_thrift
from bmv2_thrift import reset_telemetry_registers as reset_telemetry_registers_thrift
from bmv2_grpc import (  # noqa: E402
    DEFAULT_DEVICE_ID,
    DEFAULT_GRPC_ADDR,
    read_active_flows as read_active_flows_grpc,
    read_global_state as read_global_state_grpc,
    reset_telemetry_registers as reset_telemetry_registers_grpc,
)
from capture_inband import capture_from_pcap, write_jsonl  # noqa: E402
from capture_jsonl_loader import default_capture_path  # noqa: E402
from plot_capture_jsonl import plot_all  # noqa: E402
from repo_paths import task2_root
from results_paths import RESULTS_ROOT  # noqa: E402

_TASK2_ROOT = task2_root()


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture Task II telemetry and plot Task I-style figures.")
    parser.add_argument(
        "--pcap",
        type=Path,
        default=None,
        help="Optional pcap from h2; parsed into --capture-jsonl when set.",
    )
    parser.add_argument(
        "-o",
        "--capture-jsonl",
        type=Path,
        default=default_capture_path(),
        help="Capture JSONL path (used directly when --pcap is omitted).",
    )
    parser.add_argument("--results-root", type=Path, default=RESULTS_ROOT)
    parser.add_argument("-n", "--limit", type=int, default=None)
    parser.add_argument("--reset-registers", action="store_true", help="Reset BMv2 registers before capture parse.")
    parser.add_argument(
        "--use-grpc",
        action="store_true",
        help="Use P4Runtime gRPC for register reset/dump (requires make run-grpc).",
    )
    parser.add_argument("--thrift-port", type=int, default=9090, help="Thrift port when not using --use-grpc.")
    parser.add_argument(
        "--grpc-addr",
        default=DEFAULT_GRPC_ADDR,
        help=f"P4Runtime address when --use-grpc (default: {DEFAULT_GRPC_ADDR}).",
    )
    parser.add_argument("--device-id", type=int, default=DEFAULT_DEVICE_ID)
    parser.add_argument(
        "--dump-registers",
        type=Path,
        default=None,
        help="Optional path for register snapshot JSON after capture.",
    )
    parser.add_argument("--max-flows", type=int, default=16384)
    args = parser.parse_args()

    if args.reset_registers:
        try:
            if args.use_grpc:
                reset_telemetry_registers_grpc(args.grpc_addr, device_id=args.device_id)
            else:
                reset_telemetry_registers_thrift(args.thrift_port)
            print("Telemetry registers reset.")
        except (FileNotFoundError, RuntimeError) as exc:
            print(f"Register reset skipped: {exc}", file=sys.stderr)

    if args.pcap is not None:
        pcap = args.pcap if args.pcap.is_absolute() else _TASK2_ROOT / args.pcap
        records = capture_from_pcap(pcap, limit=args.limit)
        if not records:
            print("No telemetry-tagged packets found in pcap.", file=sys.stderr)
            return 1
        write_jsonl(records, args.capture_jsonl)
        print(f"Wrote {len(records):,} packets to {args.capture_jsonl}")
    elif not args.capture_jsonl.is_file():
        print(
            "Provide --pcap or an existing --capture-jsonl (e.g. from make test-mawi live capture).",
            file=sys.stderr,
        )
        return 1
    else:
        jsonl = args.capture_jsonl if args.capture_jsonl.is_absolute() else _TASK2_ROOT / args.capture_jsonl
        n_lines = sum(1 for _ in jsonl.open(encoding="utf-8"))
        if n_lines == 0:
            print(f"No packets in {jsonl}.", file=sys.stderr)
            return 1
        print(f"Using {n_lines:,} packets from {jsonl}")

    if args.dump_registers is not None:
        try:
            if args.use_grpc:
                summary = {
                    "transport": "p4runtime_grpc",
                    "grpc_addr": args.grpc_addr,
                    "device_id": args.device_id,
                    "global": read_global_state_grpc(args.grpc_addr, device_id=args.device_id),
                    "active_flows": read_active_flows_grpc(
                        args.grpc_addr,
                        device_id=args.device_id,
                        max_flows=args.max_flows,
                        min_packets=1,
                    ),
                }
            else:
                summary = {
                    "transport": "thrift_cli",
                    "thrift_port": args.thrift_port,
                    "global": read_global_state_thrift(args.thrift_port),
                    "active_flows": read_active_flows_thrift(
                        args.thrift_port,
                        max_flows=args.max_flows,
                        min_packets=1,
                    ),
                }
            args.dump_registers.parent.mkdir(parents=True, exist_ok=True)
            args.dump_registers.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            print(f"Wrote register snapshot to {args.dump_registers}")
        except (FileNotFoundError, RuntimeError) as exc:
            print(f"Register dump skipped: {exc}", file=sys.stderr)

    packets = __import__("capture_jsonl_loader").load_packets(args.capture_jsonl, limit=args.limit)
    paths = plot_all(packets, results_root=args.results_root, run_fits=True)
    print(f"Wrote {len(paths)} plots under {args.results_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
