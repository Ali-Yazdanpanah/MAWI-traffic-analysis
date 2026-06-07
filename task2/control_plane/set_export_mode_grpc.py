#!/usr/bin/env python3
"""Configure Task II telemetry export mode on BMv2 via P4Runtime gRPC."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import grpc

from bmv2_grpc import DEFAULT_DEVICE_ID, DEFAULT_GRPC_ADDR, set_telemetry_export_mode

_UTILS = Path(__file__).resolve().parents[1] / "utils"
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

from p4runtime_lib.error_utils import printGrpcError  # noqa: E402

VALID_MODES = ("inband", "udp", "both")
CAPTURE_MODE_MAP = {
    "pcap": "inband",
    "live": "inband",
    "switch": "inband",
    "udp": "udp",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set telemetry export mode via P4Runtime gRPC (make run-grpc).",
    )
    parser.add_argument(
        "--mode",
        choices=VALID_MODES,
        help="Export mode: in-band trailer, UDP INT reports, or both.",
    )
    parser.add_argument(
        "--capture-mode",
        choices=tuple(CAPTURE_MODE_MAP),
        help="Map test capture mode to switch export mode (pcap/live/switch -> inband, udp -> udp).",
    )
    parser.add_argument("--grpc-addr", default=DEFAULT_GRPC_ADDR)
    parser.add_argument("--device-id", type=int, default=DEFAULT_DEVICE_ID)
    args = parser.parse_args()

    mode = args.mode
    if mode is None and args.capture_mode is not None:
        mode = CAPTURE_MODE_MAP[args.capture_mode]
    if mode is None:
        parser.error("Provide --mode or --capture-mode")

    try:
        set_telemetry_export_mode(mode, args.grpc_addr, device_id=args.device_id)
    except grpc.RpcError as exc:
        print(f"P4Runtime error: {exc}", file=sys.stderr)
        printGrpcError(exc)
        return 1
    except (RuntimeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Telemetry export mode set to {mode} (P4Runtime gRPC).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
