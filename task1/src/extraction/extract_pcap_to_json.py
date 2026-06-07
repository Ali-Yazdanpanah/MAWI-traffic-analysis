#!/usr/bin/env python3
"""Extract packet fields from a capture to JSONL or CSV using tshark."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterator, TextIO

from tqdm import tqdm

# Progress total for 201302011400.dump(.gz) when not using -n
CAPTURE_METADATA: dict[str, int] = {
    "201302011400": 30_742_615,
}


def find_tshark() -> str:
    found = shutil.which("tshark")
    if found:
        return found
    for path in (
        r"C:\Program Files\Wireshark\tshark.exe",
        r"C:\Program Files (x86)\Wireshark\tshark.exe",
        "/usr/bin/tshark",
        "/usr/local/bin/tshark",
    ):
        if Path(path).is_file():
            return path
    raise FileNotFoundError("tshark not found — install Wireshark and add it to PATH.")


def capture_id(path: Path) -> str:
    name = path.name.removesuffix(".gz") if path.name.endswith(".gz") else path.name
    for suffix in (".dump", ".pcapng", ".pcap", ".cap"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(name).stem


def progress_total(path: Path, limit: int | None) -> int | None:
    total = CAPTURE_METADATA.get(capture_id(path))
    if limit is not None:
        return min(limit, total) if total else limit
    return total


def open_output(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "wt", encoding="utf-8", newline="")
    return path.open("w", encoding="utf-8", newline="")


def is_packet_line(line: str) -> bool:
    try:
        return "layers" in json.loads(line)
    except json.JSONDecodeError:
        return False


def stop_tshark(proc: subprocess.Popen[str], *, stopped_early: bool) -> None:
    """Terminate tshark and avoid blocking on full-file reads after -c limit."""
    if proc.stdout and not proc.stdout.closed:
        proc.stdout.close()
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    exc = sys.exc_info()[0]
    if proc.returncode not in (0, None) and not stopped_early and exc not in (
        KeyboardInterrupt,
        GeneratorExit,
    ):
        raise RuntimeError(f"tshark failed (exit {proc.returncode})")


def iter_packets(
    input_path: Path,
    *,
    include_raw: bool,
    limit: int | None,
) -> Iterator[str]:
    cmd = [find_tshark(), "-r", str(input_path), "-n", "-Q", "-T", "ek"]
    if include_raw:
        cmd.append("-x")
    # -c stops after N packets in the file (display filter alone still reads the whole capture)
    if limit is not None:
        cmd.extend(["-c", str(limit)])

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    count = 0
    stopped_early = False
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line or not is_packet_line(line):
                continue
            yield line
            count += 1
            if limit is not None and count >= limit:
                stopped_early = True
                break
    except (KeyboardInterrupt, GeneratorExit):
        stopped_early = True
        raise
    finally:
        stop_tshark(proc, stopped_early=stopped_early)


def flatten(obj: object, prefix: str = "", out: dict[str, str] | None = None) -> dict[str, str]:
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            flatten(value, child, out)
    elif isinstance(obj, (list, tuple)):
        out[prefix or "value"] = json.dumps(obj, ensure_ascii=False)
    else:
        out[prefix or "value"] = "" if obj is None else str(obj)
    return out


def write_jsonl(
    input_path: Path,
    output_path: Path,
    *,
    include_raw: bool,
    limit: int | None,
    total: int | None,
    show_progress: bool,
) -> int:
    count = 0
    bar = tqdm(total=total, unit="pkt", disable=not show_progress, file=sys.stderr)
    with open_output(output_path) as out:
        try:
            for line in iter_packets(input_path, include_raw=include_raw, limit=limit):
                out.write(line)
                out.write("\n")
                count += 1
                bar.update(1)
        finally:
            bar.close()
    return count


def write_csv(
    input_path: Path,
    output_path: Path,
    *,
    include_raw: bool,
    limit: int | None,
    total: int | None,
    show_progress: bool,
) -> int:
    count = 0
    bar = tqdm(total=total, unit="pkt", disable=not show_progress, file=sys.stderr)
    with open_output(output_path) as out:
        writer = csv.writer(out)
        writer.writerow(["packet_number", "field_path", "value"])
        try:
            for line in iter_packets(input_path, include_raw=include_raw, limit=limit):
                flat = flatten(json.loads(line))
                frame = flat.get("layers.frame.frame_frame_number", str(count + 1))
                for field_path, value in flat.items():
                    writer.writerow([frame, field_path, value])
                count += 1
                bar.update(1)
        finally:
            bar.close()
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract capture packets to JSONL or CSV.")
    parser.add_argument(
        "input_file",
        nargs="?",
        default="201302011400.dump.gz",
        help="Capture file (.dump, .pcap, .pcapng, optionally .gz)",
    )
    parser.add_argument("-o", "--output", help="Output path (default: <id>.<format>)")
    parser.add_argument(
        "-n",
        "--limit-packets",
        type=int,
        metavar="N",
        help="Read only first N packets (tshark -c; does not scan the whole capture)",
    )
    parser.add_argument(
        "--format",
        choices=("jsonl", "csv"),
        default="jsonl",
        help="jsonl = one packet per line; csv = long format (default: jsonl)",
    )
    parser.add_argument("--no-raw", action="store_true", help="Skip raw frame bytes (-x)")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bar")
    args = parser.parse_args()

    if args.limit_packets is not None and args.limit_packets <= 0:
        print("--limit-packets must be positive.", file=sys.stderr)
        return 2

    input_path = Path(args.input_file).resolve()
    if not input_path.exists():
        print(f"Not found: {input_path}", file=sys.stderr)
        return 1

    output_path = (
        Path(args.output).resolve()
        if args.output
        else input_path.parent / f"{capture_id(input_path)}.{args.format}"
    )
    total = progress_total(input_path, args.limit_packets)
    include_raw = not args.no_raw
    show_progress = not args.no_progress

    print(f"Input:  {input_path}", file=sys.stderr)
    print(f"Output: {output_path}", file=sys.stderr)
    if total:
        print(f"Progress: {total:,} packets", file=sys.stderr)

    try:
        if args.format == "jsonl":
            count = write_jsonl(
                input_path,
                output_path,
                include_raw=include_raw,
                limit=args.limit_packets,
                total=total,
                show_progress=show_progress,
            )
        else:
            count = write_csv(
                input_path,
                output_path,
                include_raw=include_raw,
                limit=args.limit_packets,
                total=total,
                show_progress=show_progress,
            )
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130

    print(f"Done. Wrote {count:,} packets.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
