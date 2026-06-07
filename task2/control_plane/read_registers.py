#!/usr/bin/env python3
"""Read Task II flow telemetry registers from BMv2 and export JSON summaries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bmv2_cli import read_active_flows, read_global_state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dump BMv2 register telemetry for Task II comparison with Task I."
    )
    parser.add_argument("--thrift-port", type=int, default=9090)
    parser.add_argument(
        "--max-flows",
        type=int,
        default=512,
        help="Scan register indices [0, max_flows) for non-zero flows (default 512).",
    )
    parser.add_argument(
        "--min-packets",
        type=int,
        default=1,
        help="Include flows with at least this many packets.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write JSON summary to this path (default: stdout only).",
    )
    args = parser.parse_args()

    try:
        global_state = read_global_state(args.thrift_port)
        flows = read_active_flows(
            args.thrift_port,
            max_flows=args.max_flows,
            min_packets=args.min_packets,
        )
    except FileNotFoundError:
        print("simple_switch_CLI not found; run inside the P4 Docker environment.", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    summary = {
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
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
