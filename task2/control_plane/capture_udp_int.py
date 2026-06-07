#!/usr/bin/env python3
"""Collect UDP INT telemetry reports via live Scapy sniff and write JSONL."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.getLogger("scapy.runtime").setLevel(logging.ERROR)

from scapy.all import conf, sniff  # type: ignore[import-untyped]

conf.verb = 0

from capture_jsonl_loader import default_capture_path, parse_int_report_record
from telemetry_decode import INT_COLLECTOR_PORT, INT_REPORT_MAGIC_BYTES


def capture_udp_to_jsonl(
    interface: str,
    port: int,
    output: Path,
    *,
    timeout: int | None = None,
    limit: int | None = None,
) -> int:
    """Sniff UDP INT reports on a live interface and stream JSONL records."""
    from scapy.all import UDP  # type: ignore[import-untyped]

    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0

    with output.open("w", encoding="utf-8") as handle:

        def _on_packet(pkt) -> None:  # noqa: ANN001
            nonlocal written
            if limit is not None and written >= limit:
                return
            if UDP not in pkt:
                return
            udp = pkt[UDP]
            if int(udp.dport) != port:
                return
            payload = bytes(udp.payload)
            if len(payload) < len(INT_REPORT_MAGIC_BYTES) or payload[:4] != INT_REPORT_MAGIC_BYTES:
                return
            row = parse_int_report_record(
                written + 1,
                payload,
                time_epoch=float(pkt.time),
            )
            if row is None:
                return
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            written += 1

        def _stop_filter(_pkt) -> bool:  # noqa: ANN001
            return limit is not None and written >= limit

        sniff(
            iface=interface,
            filter=f"udp and port {port}",
            prn=_on_packet,
            store=False,
            timeout=timeout,
            count=0,
            stop_filter=_stop_filter if limit is not None else None,
        )

    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture UDP INT reports on a live interface into JSONL.",
    )
    parser.add_argument(
        "--interface",
        required=True,
        help="Mininet host NIC (e.g. eth0 inside h2 via mnexec).",
    )
    parser.add_argument(
        "--udp-port",
        type=int,
        default=INT_COLLECTOR_PORT,
        help=f"UDP collector port (default: {INT_COLLECTOR_PORT}).",
    )
    parser.add_argument("--timeout", type=int, default=None, help="Sniff timeout in seconds.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=default_capture_path(),
        help=f"Output JSONL (default: {default_capture_path()})",
    )
    parser.add_argument("-n", "--limit", type=int, default=None, help="Max INT reports to export.")
    args = parser.parse_args()

    try:
        written = capture_udp_to_jsonl(
            args.interface,
            args.udp_port,
            args.output,
            timeout=args.timeout,
            limit=args.limit,
        )
        if written == 0:
            print("No UDP INT reports received.", file=sys.stderr)
            return 1
        print(f"Wrote {written:,} INT reports to {args.output}")
        return 0
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
