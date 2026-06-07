#!/usr/bin/env python3
"""Capture BMv2 telemetry trailers from h2 and write Task II JSONL."""

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

from bootstrap import default_capture_path, parse_captured_frame, parse_int_report_record
from paths import task2_root
from telemetry import INT_COLLECTOR_PORT

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


def capture_live(
    interface: str,
    *,
    count: int,
    timeout: int | None = None,
    limit: int | None = None,
) -> list[dict]:
    records: list[dict] = []

    def _on_packet(pkt) -> None:  # noqa: ANN001
        if limit is not None and len(records) >= limit:
            return
        if len(records) >= count:
            return
        raw = _packet_raw_bytes(pkt)
        row = parse_captured_frame(len(records) + 1, raw)
        if row is not None:
            records.append(row)

    sniff(iface=interface, prn=_on_packet, store=False, timeout=timeout, count=count)
    if limit is not None:
        return records[:limit]
    return records


def capture_live_to_jsonl(
    interface: str,
    output: Path,
    *,
    timeout: int | None = None,
    limit: int | None = None,
    sniff_count: int = 0,
) -> int:
    """Sniff telemetry on a live interface and stream JSONL records to disk."""
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
        description="Parse telemetry from pcap, live sniff, or UDP INT reports into JSONL."
    )
    parser.add_argument("--pcap", type=Path, help="Offline pcap captured on h2 (port-2 egress).")
    parser.add_argument(
        "--interface",
        help="Live capture on Mininet host NIC (e.g. eth0 inside h2 via mnexec).",
    )
    parser.add_argument(
        "--int-udp",
        action="store_true",
        help="With --interface, capture UDP INT reports instead of in-band telemetry.",
    )
    parser.add_argument(
        "--udp-port",
        type=int,
        default=INT_COLLECTOR_PORT,
        help=f"UDP collector port when --int-udp is set (default: {INT_COLLECTOR_PORT}).",
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
    if args.int_udp and args.interface is None:
        parser.error("--int-udp requires --interface")

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

        if args.int_udp:
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
