#!/usr/bin/env python3
"""Read Task II flow telemetry registers from BMv2 via P4Runtime gRPC."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import grpc

from bmv2_grpc import (
    DEFAULT_DEVICE_ID,
    DEFAULT_GRPC_ADDR,
    read_active_flows,
    read_global_state,
)

_UTILS = Path(__file__).resolve().parents[1] / "utils"
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

from p4runtime_lib.error_utils import printGrpcError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dump BMv2 register telemetry via P4Runtime gRPC (Task II).",
    )
    parser.add_argument(
        "--grpc-addr",
        default=DEFAULT_GRPC_ADDR,
        help=f"P4Runtime server address (default: {DEFAULT_GRPC_ADDR})",
    )
    parser.add_argument("--device-id", type=int, default=DEFAULT_DEVICE_ID)
    parser.add_argument(
        "--max-flows",
        type=int,
        default=16384,
        help="Scan register indices [0, max_flows) for non-zero flows.",
    )
    parser.add_argument(
        "--min-packets",
        type=int,
        default=1,
        help="Include flows with at least this many packets.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write JSON summary to this path (default: stdout only).",
    )
    args = parser.parse_args()

    try:
        global_state = read_global_state(args.grpc_addr, device_id=args.device_id)
        flows = read_active_flows(
            args.grpc_addr,
            device_id=args.device_id,
            max_flows=args.max_flows,
            min_packets=args.min_packets,
        )
    except grpc.RpcError as exc:
        print(f"P4Runtime error: {exc}", file=sys.stderr)
        printGrpcError(exc)
        print("Ensure Mininet is running with: make run-grpc", file=sys.stderr)
        print(
            "For Thrift register reads use: python3 control_plane/read_registers_thrift.py",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    summary = {
        "transport": "p4runtime_grpc",
        "grpc_addr": args.grpc_addr,
        "device_id": args.device_id,
        "global": global_state,
        "active_flows": flows,
        "collision_note": (
            "flow_id = CRC16(canonical 5-tuple) mod 16384. "
            "Hash collisions merge distinct flows; discuss in Task III."
        ),
        "byte_count_note": (
            "byte_count sums L3 length (IPv4 totalLen / IPv6 payload+40). "
            "Task I frame_len is L2 and MAWI truncates at 96 B."
        ),
    }

    payload = json.dumps(summary, indent=2)
    print(payload)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
