#!/usr/bin/env python3
"""Configure Task II telemetry export mode on BMv2 (in-band, UDP INT, or both)."""

from __future__ import annotations

import argparse
import sys

from bmv2_cli import set_telemetry_export_mode as set_telemetry_export_mode_thrift
from bmv2_grpc import DEFAULT_DEVICE_ID, DEFAULT_GRPC_ADDR, set_telemetry_export_mode as set_telemetry_export_mode_grpc

VALID_MODES = ("inband", "udp", "both")
CAPTURE_MODE_MAP = {
    "pcap": "inband",
    "live": "inband",
    "switch": "inband",
    "udp": "udp",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select telemetry export path on the switch before MAWI replay."
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
    parser.add_argument("--use-grpc", action="store_true", help="Use P4Runtime gRPC (make run-grpc).")
    parser.add_argument("--thrift-port", type=int, default=9090)
    parser.add_argument("--grpc-addr", default=DEFAULT_GRPC_ADDR)
    parser.add_argument("--device-id", type=int, default=DEFAULT_DEVICE_ID)
    args = parser.parse_args()

    mode = args.mode
    if mode is None and args.capture_mode is not None:
        mode = CAPTURE_MODE_MAP[args.capture_mode]
    if mode is None:
        parser.error("Provide --mode or --capture-mode")

    try:
        if args.use_grpc:
            set_telemetry_export_mode_grpc(
                mode,
                args.grpc_addr,
                device_id=args.device_id,
            )
        else:
            set_telemetry_export_mode_thrift(args.thrift_port, mode)
    except FileNotFoundError:
        print("simple_switch_CLI not found; use --use-grpc with make run-grpc.", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Telemetry export mode set to {mode}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
