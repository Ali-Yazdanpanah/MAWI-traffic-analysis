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

try:
    import bmv2_cli
except ImportError:
    bmv2_cli = None  # type: ignore[assignment]

_DEFAULT_THRIFT_PORT = 9090


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
        "--thrift-port",
        type=int,
        default=_DEFAULT_THRIFT_PORT,
        help=(
            "Fallback Thrift port when P4Runtime register reads are unsupported "
            f"(default: {_DEFAULT_THRIFT_PORT}; requires simple_switch_grpc built with --with-thrift)."
        ),
    )
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

    transport = "p4runtime_grpc"
    try:
        global_state = read_global_state(args.grpc_addr, device_id=args.device_id)
        flows = read_active_flows(
            args.grpc_addr,
            device_id=args.device_id,
            max_flows=args.max_flows,
            min_packets=args.min_packets,
        )
    except grpc.RpcError as exc:
        if bmv2_cli is None or exc.code() not in (
            grpc.StatusCode.UNIMPLEMENTED,
            grpc.StatusCode.UNKNOWN,
        ):
            print(f"P4Runtime error: {exc}", file=sys.stderr)
            print("Is Mininet running with make run-grpc?", file=sys.stderr)
            return 1
        try:
            global_state = bmv2_cli.read_global_state(args.thrift_port)
            flows = bmv2_cli.read_active_flows(
                args.thrift_port,
                max_flows=args.max_flows,
                min_packets=args.min_packets,
            )
            transport = "thrift_fallback"
            print(
                "Note: BMv2 does not support P4Runtime register reads (PI#376); "
                f"used simple_switch_CLI on port {args.thrift_port}.",
                file=sys.stderr,
            )
        except Exception as fallback_exc:
            print(f"P4Runtime error: {exc}", file=sys.stderr)
            print(
                "Register reads are not implemented over P4Runtime on BMv2. "
                "Use make run + read_registers.py, or parse in-band telemetry from data/capture.pcap.",
                file=sys.stderr,
            )
            print(f"Thrift fallback failed: {fallback_exc}", file=sys.stderr)
            return 1
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    summary = {
        "transport": transport,
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
