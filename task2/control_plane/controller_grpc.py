#!/usr/bin/env python3
"""Reset Task II telemetry registers on BMv2 via P4Runtime gRPC."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import grpc

from bmv2_grpc import DEFAULT_DEVICE_ID, DEFAULT_GRPC_ADDR, reset_telemetry_registers

_UTILS = Path(__file__).resolve().parents[1] / "utils"
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

from p4runtime_lib.error_utils import printGrpcError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset BMv2 telemetry registers (Task II) via P4Runtime gRPC.",
    )
    parser.add_argument(
        "--grpc-addr",
        default=DEFAULT_GRPC_ADDR,
        help=f"P4Runtime server address (default: {DEFAULT_GRPC_ADDR})",
    )
    parser.add_argument("--device-id", type=int, default=DEFAULT_DEVICE_ID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print(f"[dry-run] would reset registers via gRPC at {args.grpc_addr}")
        return 0

    try:
        reset_telemetry_registers(args.grpc_addr, device_id=args.device_id)
    except grpc.RpcError as exc:
        print(f"P4Runtime error: {exc}", file=sys.stderr)
        printGrpcError(exc)
        print("Ensure Mininet is running with: make run-grpc", file=sys.stderr)
        print("If you changed topology/runtime files, exit mininet and restart make run-grpc.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print("Telemetry registers reset via P4Runtime (pipeline reload).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
