#!/usr/bin/env python3
"""Reset Task II telemetry registers on BMv2 before trace replay."""

from __future__ import annotations

import argparse
import sys

from bmv2_cli import reset_telemetry_registers


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset BMv2 telemetry registers (Task II) via simple_switch_CLI."
    )
    parser.add_argument("--thrift-port", type=int, default=9090)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("[dry-run] would reset MyIngress telemetry registers")
        return 0

    try:
        reset_telemetry_registers(args.thrift_port)
    except FileNotFoundError:
        print("simple_switch_CLI not found; install behavioral-model or run inside Docker.", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    print("Telemetry registers reset.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
