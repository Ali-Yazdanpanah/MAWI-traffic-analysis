"""Load Task II captures into Task I-compatible pandas DataFrames."""

from __future__ import annotations

import json
import socket
import struct
import sys
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from paths import ensure_task1_on_path, task2_root

ensure_task1_on_path()

from analysis.bootstrap import (  # noqa: E402
    FLOW_COLUMNS,
    PACKET_COLUMNS,
    classify_flow_size_class,
    _app_from_ports,
    _infer_packet_role,
    _proto_name,
)

from telemetry import split_telemetry, unpack_int_report  # noqa: E402

_DEFAULT_CAPTURE = task2_root() / "data" / "capture.jsonl"


def default_capture_path() -> Path:
    return _DEFAULT_CAPTURE


def _scapy():  # lazy — not needed when loading pre-parsed JSONL
    from scapy.all import ICMP, IP, IPv6, TCP, UDP, Ether  # type: ignore[import-untyped]

    return ICMP, IP, IPv6, TCP, UDP, Ether


def _transport_from_ip(ip_layer: Any) -> tuple[str | None, int | None, int | None, int | None, int | None]:
    ICMP, IP, IPv6, TCP, UDP, Ether = _scapy()
    del IP, IPv6, Ether
    transport = None
    src_port = dst_port = icmp_type = icmp_code = None
    if ip_layer is None:
        return transport, src_port, dst_port, icmp_type, icmp_code

    if ip_layer.haslayer(TCP):
        transport = "tcp"
        tcp = ip_layer[TCP]
        src_port = int(tcp.sport)
        dst_port = int(tcp.dport)
    elif ip_layer.haslayer(UDP):
        transport = "udp"
        udp = ip_layer[UDP]
        src_port = int(udp.sport)
        dst_port = int(udp.dport)
    elif ip_layer.haslayer(ICMP):
        transport = "icmp"
        icmp = ip_layer[ICMP]
        icmp_type = int(icmp.type)
        icmp_code = int(icmp.code)
    return transport, src_port, dst_port, icmp_type, icmp_code


def _l3_byte_len(ip_layer: Any) -> int | None:
    _, IP, IPv6, _, _, _ = _scapy()
    if ip_layer is None:
        return None
    if isinstance(ip_layer, IP):
        return int(ip_layer.len)
    if isinstance(ip_layer, IPv6):
        return int(ip_layer.plen) + 40
    return None


def _ipv4_from_int(value: int) -> str | None:
    if value == 0:
        return None
    return socket.inet_ntoa(struct.pack("!I", value & 0xFFFFFFFF))


def parse_int_report_record(
    frame_number: int,
    payload: bytes,
    *,
    time_epoch: float | None = None,
) -> dict[str, Any] | None:
    """Build a Task I-style packet record from a UDP INT report payload."""
    try:
        report = unpack_int_report(payload)
    except (struct.error, ValueError):
        return None

    ip_version = int(report["ip_version"]) if report["ip_version"] else None
    ip_proto = int(report["ip_proto"]) if report["ip_proto"] else None
    src_port = int(report["src_port"]) if report["src_port"] else None
    dst_port = int(report["dst_port"]) if report["dst_port"] else None
    frame_len = int(report["l3_byte_len"]) if report["l3_byte_len"] else None

    ip_src = ip_dst = ipv6_src = ipv6_dst = None
    if ip_version == 4:
        ip_src = _ipv4_from_int(int(report["ipv4_src"]))
        ip_dst = _ipv4_from_int(int(report["ipv4_dst"]))
        protocols = "eth:ethertype:ip"
    elif ip_version == 6:
        protocols = "eth:ethertype:ipv6"
    else:
        protocols = "int:udp"

    transport = None
    icmp_type = icmp_code = None
    if ip_proto == 6:
        transport = "tcp"
    elif ip_proto == 17:
        transport = "udp"
    elif ip_proto == 1:
        transport = "icmp"
    if transport:
        protocols = f"{protocols}:{transport}"

    if time_epoch is None:
        time_epoch = report["flow_last_ts_us"] / 1_000_000.0
    time_delta = report["iat_s"] if report["iat_valid"] else None

    tcp_len = None
    if transport == "tcp" and frame_len is not None:
        tcp_len = max(frame_len - 20, 0) if ip_version == 4 else max(frame_len - 40, 0)

    app_proto = _app_from_ports(src_port, dst_port, transport)
    packet_role = _infer_packet_role(transport, tcp_len, None)

    return {
        "capture_timestamp_ms": int(time_epoch * 1000),
        "frame_number": frame_number,
        "time_epoch": time_epoch,
        "time_delta": time_delta,
        "frame_len": frame_len,
        "protocols": protocols,
        "ip_version": ip_version,
        "ip_src": ip_src,
        "ip_dst": ip_dst,
        "ipv6_src": ipv6_src,
        "ipv6_dst": ipv6_dst,
        "src_host": ip_src or ipv6_src,
        "dst_host": ip_dst or ipv6_dst,
        "ip_proto": ip_proto,
        "ip_proto_name": _proto_name(ip_proto) if ip_proto is not None else None,
        "ip_ttl": None,
        "ip_len": frame_len,
        "transport_proto": transport,
        "l4_proto": transport,
        "app_proto": app_proto,
        "src_port": src_port,
        "dst_port": dst_port,
        "tcp_stream": None,
        "udp_stream": None,
        "tcp_len": tcp_len,
        "tcp_flags": None,
        "tcp_time_delta": None,
        "udp_time_delta": None,
        "icmp_type": icmp_type,
        "icmp_code": icmp_code,
        "packet_role": packet_role,
        "p4_flow_id": int(report["p4_flow_id"]),
        "p4_flow_pkt_count": int(report["flow_pkt_count"]),
        "p4_flow_byte_count": int(report["flow_byte_count"]),
    }


def parse_captured_frame(
    frame_number: int,
    raw: bytes,
    *,
    time_epoch: float | None = None,
) -> dict[str, Any] | None:
    ICMP, IP, IPv6, TCP, UDP, Ether = _scapy()
    del ICMP, UDP

    payload, tele = split_telemetry(raw)
    if tele is None:
        return None

    try:
        eth = Ether(payload)
    except Exception:
        return None

    ip_layer = eth.getlayer(IP) or eth.getlayer(IPv6)
    if ip_layer is None:
        return None

    if isinstance(ip_layer, IP):
        ip_version = 4
        ip_proto = int(ip_layer.proto)
        ip_src = str(ip_layer.src)
        ip_dst = str(ip_layer.dst)
        ipv6_src = ipv6_dst = None
        protocols = "eth:ethertype:ip"
    else:
        ip_version = 6
        ip_proto = int(ip_layer.nh)
        ipv6_src = str(ip_layer.src)
        ipv6_dst = str(ip_layer.dst)
        ip_src = ip_dst = None
        protocols = "eth:ethertype:ipv6"

    transport, src_port, dst_port, icmp_type, icmp_code = _transport_from_ip(ip_layer)
    if transport:
        protocols = f"{protocols}:{transport}"

    frame_len = _l3_byte_len(ip_layer)
    if time_epoch is None:
        time_epoch = tele["flow_last_ts_us"] / 1_000_000.0
    time_delta = tele["iat_s"] if tele["iat_valid"] else None

    tcp_len = None
    if transport == "tcp" and ip_layer.haslayer(TCP):
        # Logical tcp_len from header math (matches tshark tcp.len on MAWI truncation).
        tcp_header_len = int(ip_layer[TCP].dataofs) * 4
        if isinstance(ip_layer, IP):
            ip_total_len = int(ip_layer.len)
            ip_header_len = int(ip_layer.ihl) * 4
            logical_len = ip_total_len - ip_header_len - tcp_header_len
        else:
            ipv6_payload_len = int(ip_layer.plen)
            logical_len = ipv6_payload_len - tcp_header_len
        tcp_len = max(logical_len, 0)

    app_proto = _app_from_ports(src_port, dst_port, transport)
    packet_role = _infer_packet_role(transport, tcp_len, None)

    return {
        "capture_timestamp_ms": int(time_epoch * 1000),
        "frame_number": frame_number,
        "time_epoch": time_epoch,
        "time_delta": time_delta,
        "frame_len": frame_len,
        "protocols": protocols,
        "ip_version": ip_version,
        "ip_src": ip_src,
        "ip_dst": ip_dst,
        "ipv6_src": ipv6_src,
        "ipv6_dst": ipv6_dst,
        "src_host": ip_src or ipv6_src,
        "dst_host": ip_dst or ipv6_dst,
        "ip_proto": ip_proto,
        "ip_proto_name": _proto_name(ip_proto),
        "ip_ttl": int(ip_layer.ttl) if isinstance(ip_layer, IP) else None,
        "ip_len": int(ip_layer.len) if isinstance(ip_layer, IP) else int(ip_layer.plen) + 40,
        "transport_proto": transport,
        "l4_proto": transport,
        "app_proto": app_proto,
        "src_port": src_port,
        "dst_port": dst_port,
        "tcp_stream": None,
        "udp_stream": None,
        "tcp_len": tcp_len,
        "tcp_flags": None,
        "tcp_time_delta": None,
        "udp_time_delta": None,
        "icmp_type": icmp_type,
        "icmp_code": icmp_code,
        "packet_role": packet_role,
        "p4_flow_id": int(tele["p4_flow_id"]),
        "p4_flow_pkt_count": int(tele["flow_pkt_count"]),
        "p4_flow_byte_count": int(tele["flow_byte_count"]),
    }


def iter_capture_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _normalize_time_epochs(df: pd.DataFrame) -> pd.DataFrame:
    """Map BMv2/P4 microsecond clocks to a matplotlib-safe relative timeline."""
    if df.empty or "time_epoch" not in df.columns:
        return df
    epochs = pd.to_numeric(df["time_epoch"], errors="coerce")
    anchor = epochs.min()
    if pd.isna(anchor):
        return df
    out = df.copy()
    out["time_epoch"] = epochs - anchor
    if "capture_timestamp_ms" in out.columns:
        out["capture_timestamp_ms"] = (out["time_epoch"] * 1000).round().astype("Int64")
    return out


def load_packets(
    path: str | Path | None = None,
    *,
    limit: int | None = None,
    sort: bool = True,
) -> pd.DataFrame:
    resolved = Path(path) if path is not None else default_capture_path()
    if not resolved.is_file():
        raise FileNotFoundError(f"Capture JSONL not found: {resolved}")

    rows: list[dict[str, Any]] = []
    for record in iter_capture_jsonl(resolved):
        rows.append(record)
        if limit is not None and len(rows) >= limit:
            break

    if not rows:
        return pd.DataFrame(columns=PACKET_COLUMNS)

    df = pd.DataFrame(rows)
    for col in PACKET_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    extra = [c for c in df.columns if c not in PACKET_COLUMNS]
    df = df[PACKET_COLUMNS + extra]

    int_cols = [
        "capture_timestamp_ms",
        "frame_number",
        "frame_len",
        "ip_version",
        "ip_proto",
        "ip_ttl",
        "ip_len",
        "src_port",
        "dst_port",
        "icmp_type",
        "icmp_code",
        "p4_flow_id",
        "p4_flow_pkt_count",
        "p4_flow_byte_count",
    ]
    float_cols = ["time_epoch", "time_delta"]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if sort:
        df = df.sort_values("frame_number", kind="mergesort").reset_index(drop=True)
    return _normalize_time_epochs(df)


def load_flows(
    packets: pd.DataFrame | None = None,
    *,
    path: str | Path | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    if packets is None:
        packets = load_packets(path, limit=limit)
    if packets.empty or "p4_flow_id" not in packets.columns:
        return pd.DataFrame(columns=FLOW_COLUMNS)

    work = packets.copy()
    work["flow_id"] = "p4:" + work["p4_flow_id"].astype("Int64").astype(str)

    grouped = work.groupby("flow_id", sort=False)
    flows = grouped.agg(
        transport_proto=("transport_proto", "first"),
        l4_proto=("l4_proto", "first"),
        app_proto=("app_proto", "first"),
        ip_version=("ip_version", "first"),
        src_host=("src_host", "first"),
        dst_host=("dst_host", "first"),
        ip_src=("ip_src", "first"),
        ip_dst=("ip_dst", "first"),
        ip_proto=("ip_proto", "first"),
        src_port=("src_port", "first"),
        dst_port=("dst_port", "first"),
        tcp_stream=("tcp_stream", "first"),
        udp_stream=("udp_stream", "first"),
        start_epoch=("time_epoch", "min"),
        end_epoch=("time_epoch", "max"),
        packet_count=("frame_number", "count"),
        byte_sum=("frame_len", "sum"),
    ).reset_index()

    flows["duration"] = flows["end_epoch"] - flows["start_epoch"]
    flows["throughput_bps"] = flows.apply(
        lambda r: (r["byte_sum"] * 8 / r["duration"]) if r["duration"] and r["duration"] > 0 else pd.NA,
        axis=1,
    )
    flows["flow_size_class"] = classify_flow_size_class(flows["byte_sum"])
    return flows[FLOW_COLUMNS]
