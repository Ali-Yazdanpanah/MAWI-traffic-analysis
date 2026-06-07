#!/usr/bin/env python3
"""Configure Task II telemetry export mode on BMv2 via Thrift (simple_switch_CLI)."""

from __future__ import annotations

import argparse
import sys

from bmv2_thrift import set_telemetry_export_mode

VALID_MODES = ("inband", "udp", "both")
CAPTURE_MODE_MAP = {
    "pcap": "inband",
    "live": "inband",
    "switch": "inband",
    "udp": "udp",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set telemetry export mode via Thrift (make run-thrift / simple_switch).",
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
    parser.add_argument("--thrift-port", type=int, default=9090)
    args = parser.parse_args()

    mode = args.mode
    if mode is None and args.capture_mode is not None:
        mode = CAPTURE_MODE_MAP[args.capture_mode]
    if mode is None:
        parser.error("Provide --mode or --capture-mode")

    try:
        set_telemetry_export_mode(args.thrift_port, mode)
    except FileNotFoundError:
        print("simple_switch_CLI not found; run inside the P4 Docker environment (make run-thrift).", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"Telemetry export mode set to {mode} (Thrift).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
