#!/usr/bin/env python3
"""Collect in-band telemetry (pcap file or live Scapy sniff) and write JSONL."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.getLogger("scapy.runtime").setLevel(logging.ERROR)

from scapy.all import conf, sniff  # type: ignore[import-untyped]
from scapy.utils import PcapReader  # type: ignore[import-untyped]

conf.verb = 0

from capture_jsonl_loader import default_capture_path, parse_captured_frame
from repo_paths import task2_root

_TASK2_ROOT = task2_root()


def _packet_raw_bytes(pkt) -> bytes:  # noqa: ANN001
    """Use on-disk frame bytes; avoid Scapy rebuild (slow + MAC warnings)."""
    original = getattr(pkt, "original", None)
    if original is not None:
        return bytes(original)
    return bytes(pkt)


def write_jsonl(records: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def capture_from_pcap(pcap_path: Path, *, limit: int | None = None) -> list[dict]:
    records: list[dict] = []
    with PcapReader(str(pcap_path)) as reader:
        for idx, pkt in enumerate(reader, start=1):
            raw = _packet_raw_bytes(pkt)
            row = parse_captured_frame(idx, raw, time_epoch=float(pkt.time))
            if row is None:
                continue
            records.append(row)
            if limit is not None and len(records) >= limit:
                break
    return records


def capture_live_to_jsonl(
    interface: str,
    output: Path,
    *,
    timeout: int | None = None,
    limit: int | None = None,
    sniff_count: int = 0,
) -> int:
    """Sniff in-band telemetry on a live interface and stream JSONL records to disk."""
    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0

    with output.open("w", encoding="utf-8") as handle:

        def _on_packet(pkt) -> None:  # noqa: ANN001
            nonlocal written
            if limit is not None and written >= limit:
                return
            raw = _packet_raw_bytes(pkt)
            row = parse_captured_frame(written + 1, raw)
            if row is None:
                return
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            written += 1

        def _stop_filter(_pkt) -> bool:  # noqa: ANN001
            return limit is not None and written >= limit

        sniff(
            iface=interface,
            prn=_on_packet,
            store=False,
            timeout=timeout,
            count=sniff_count,
            stop_filter=_stop_filter if limit is not None else None,
        )

    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse in-band telemetry from pcap or live sniff into JSONL.",
    )
    parser.add_argument("--pcap", type=Path, help="Offline pcap (h2 tcpdump or switch port 2).")
    parser.add_argument(
        "--interface",
        help="Live in-band sniff on Mininet host NIC (e.g. eth0 inside h2).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Max raw frames to sniff on --interface (0 = unlimited until -n or --timeout).",
    )
    parser.add_argument("--timeout", type=int, default=None, help="Live sniff timeout in seconds.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=default_capture_path(),
        help=f"Output JSONL (default: {default_capture_path()})",
    )
    parser.add_argument("-n", "--limit", type=int, default=None, help="Max packets to export.")
    args = parser.parse_args()

    if args.pcap is not None and args.interface is not None:
        parser.error("Use only one of --pcap or --interface")
    if args.pcap is None and args.interface is None:
        parser.error("Provide --pcap or --interface")

    try:
        if args.pcap is not None:
            pcap = args.pcap if args.pcap.is_absolute() else _TASK2_ROOT / args.pcap
            records = capture_from_pcap(pcap, limit=args.limit)
            if not records:
                print("No telemetry-tagged packets found.", file=sys.stderr)
                return 1
            write_jsonl(records, args.output)
            print(f"Wrote {len(records):,} packets to {args.output}")
            return 0

        count = args.count if args.count > 0 else 0
        written = capture_live_to_jsonl(
            args.interface,
            args.output,
            timeout=args.timeout,
            limit=args.limit,
            sniff_count=count,
        )
        if written == 0:
            print("No telemetry-tagged packets found.", file=sys.stderr)
            return 1
        print(f"Wrote {written:,} packets to {args.output}")
        return 0
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
