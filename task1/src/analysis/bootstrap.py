#!/usr/bin/env python3
"""Bootstrap MAWI tshark JSONL into pandas DataFrames for Task I analyses."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

# Repo root: .../task1/src/analysis/bootstrap.py -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_JSONL = _REPO_ROOT / "201302011400.jsonl"

# IANA IP protocol numbers -> name (common values in MAWI traces).
IP_PROTO_NAMES: dict[int, str] = {
    0: "hopopt",
    1: "icmp",
    2: "igmp",
    6: "tcp",
    17: "udp",
    41: "ipv6",
    43: "routing",
    44: "fragment",
    47: "gre",
    50: "esp",
    51: "ah",
    58: "icmpv6",
    89: "ospf",
    132: "sctp",
}

# Dissector layer keys checked in priority order (transport / network helpers).
_TRANSPORT_LAYER_KEYS = ("tcp", "udp", "icmp", "icmpv6", "esp", "gre")

# Stack tokens that are not application protocols (link/network/transport).
_STACK_SKIP_TOKENS = frozenset(
    {
        "eth",
        "ethertype",
        "ip",
        "ipv6",
        "tcp",
        "udp",
        "icmp",
        "icmpv6",
        "gre",
        "esp",
        "ospf",
        "ipv6.fraghdr",
        "fragment",
        "sll",
        "vlan",
        "mpls",
    }
)

# Wireshark layer/stack token -> normalized app_proto name.
_APP_ALIASES: dict[str, str] = {
    "dns": "dns",
    "mdns": "mdns",
    "llmnr": "llmnr",
    "dhcp": "dhcp",
    "bootp": "dhcp",
    "http": "http",
    "http2": "http2",
    "tls": "tls",
    "ssl": "tls",
    "dtls": "dtls",
    "quic": "quic",
    "ssh": "ssh",
    "ftp": "ftp",
    "ftp-data": "ftp-data",
    "smtp": "smtp",
    "pop": "pop3",
    "pop3": "pop3",
    "imap": "imap",
    "telnet": "telnet",
    "rdp": "rdp",
    "sip": "sip",
    "rtp": "rtp",
    "rtsp": "rtsp",
    "snmp": "snmp",
    "ntp": "ntp",
    "ldap": "ldap",
    "krb5": "kerberos",
    "smb": "smb",
    "smb2": "smb",
    "nbns": "netbios",
    "nbss": "netbios",
    "ssdp": "ssdp",
    "bitcoin": "bitcoin",
    "mysql": "mysql",
    "pgsql": "postgres",
    "redis": "redis",
    "mqtt": "mqtt",
}

# Dissector layers checked before stack/ports (higher confidence).
_APP_LAYER_PRIORITY = (
    "dns",
    "mdns",
    "dhcp",
    "http2",
    "http",
    "tls",
    "ssl",
    "dtls",
    "quic",
    "ssh",
    "ftp-data",
    "ftp",
    "smtp",
    "pop3",
    "pop",
    "imap",
    "telnet",
    "rdp",
    "sip",
    "rtp",
    "rtsp",
    "snmp",
    "ntp",
    "ldap",
    "krb5",
    "smb2",
    "smb",
    "nbns",
    "nbss",
    "ssdp",
    "bitcoin",
    "mysql",
    "pgsql",
    "redis",
    "mqtt",
)

# Well-known ports -> app_proto (heuristic; used when dissector stops at tcp/udp).
_WELL_KNOWN_PORTS: dict[int, str] = {
    20: "ftp-data",
    21: "ftp",
    22: "ssh",
    23: "telnet",
    25: "smtp",
    53: "dns",
    67: "dhcp",
    68: "dhcp",
    69: "tftp",
    80: "http",
    110: "pop3",
    123: "ntp",
    143: "imap",
    161: "snmp",
    162: "snmp",
    389: "ldap",
    443: "tls",
    445: "smb",
    465: "smtps",
    514: "syslog",
    587: "smtp",
    636: "ldaps",
    993: "imaps",
    995: "pop3s",
    1433: "mssql",
    1521: "oracle",
    1883: "mqtt",
    3306: "mysql",
    3389: "rdp",
    5060: "sip",
    5222: "xmpp",
    5432: "postgres",
    5900: "vnc",
    6379: "redis",
    8080: "http",
    8443: "tls",
    853: "dns",  # DNS over TLS
    5353: "mdns",
    1900: "ssdp",
}

# Canonical packet columns used by time-series, host, topology, and packet analyses.
PACKET_COLUMNS = [
    "capture_timestamp_ms",
    "frame_number",
    "time_epoch",
    "time_delta",
    "frame_len",
    "protocols",
    "ip_version",
    "ip_src",
    "ip_dst",
    "ipv6_src",
    "ipv6_dst",
    "src_host",
    "dst_host",
    "ip_proto",
    "ip_proto_name",
    "ip_ttl",
    "ip_len",
    "transport_proto",
    "l4_proto",
    "app_proto",
    "src_port",
    "dst_port",
    "tcp_stream",
    "udp_stream",
    "tcp_len",
    "tcp_flags",
    "tcp_time_delta",
    "udp_time_delta",
    "icmp_type",
    "icmp_code",
    "packet_role",
]

FLOW_COLUMNS = [
    "flow_id",
    "transport_proto",
    "l4_proto",
    "app_proto",
    "ip_version",
    "src_host",
    "dst_host",
    "ip_src",
    "ip_dst",
    "ip_proto",
    "src_port",
    "dst_port",
    "tcp_stream",
    "udp_stream",
    "start_epoch",
    "end_epoch",
    "duration",
    "packet_count",
    "byte_sum",
    "throughput_bps",
    "flow_size_class",
]


def default_jsonl_path() -> Path:
    """Default path to the MAWI JSONL export at the repo root."""
    return _DEFAULT_JSONL


def resolve_jsonl_path(path: str | Path | None = None) -> Path:
    resolved = Path(path) if path is not None else default_jsonl_path()
    if not resolved.is_file():
        raise FileNotFoundError(f"JSONL not found: {resolved}")
    return resolved


def _layer(layers: dict[str, Any], name: str) -> dict[str, Any]:
    layer = layers.get(name)
    return layer if isinstance(layer, dict) else {}


def _first_scalar(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _protocol_stack(protocols: str | None) -> list[str]:
    if not protocols:
        return []
    return [part for part in protocols.split(":") if part]


def _proto_name(proto_num: int | None) -> str | None:
    if proto_num is None:
        return None
    return IP_PROTO_NAMES.get(proto_num, f"ipproto-{proto_num}")


def _infer_transport_proto(
    layers: dict[str, Any],
    *,
    protocols: str | None,
    ip_proto: int | None,
    ipv6_nxt: int | None,
) -> str | None:
    """Classify transport/network protocol from dissector layers and headers."""
    for key in _TRANSPORT_LAYER_KEYS:
        if key in layers:
            return key

    stack = _protocol_stack(protocols)
    if "gre" in stack or ip_proto == 47 or ipv6_nxt == 47:
        return "gre"
    if "esp" in stack or ip_proto == 50 or ipv6_nxt == 50:
        return "esp"
    if "icmpv6" in stack or ip_proto == 58 or ipv6_nxt == 58:
        return "icmpv6"
    if "icmp" in stack or ip_proto == 1 or ipv6_nxt == 1:
        return "icmp"
    if any(token in stack for token in ("ipv6.fraghdr", "fragment")):
        return "ipv6-frag"
    if "ipv6" in layers and "ip" not in layers:
        return "ipv6"
    if ip_proto is not None:
        return _proto_name(ip_proto)
    if ipv6_nxt is not None:
        return _proto_name(ipv6_nxt)
    if stack:
        # Last token is often the innermost dissector (e.g. dns, tcp).
        return stack[-1].replace(".", "-")
    return None


def _normalize_app_token(token: str) -> str | None:
    key = token.strip().lower().replace(".", "-")
    return _APP_ALIASES.get(key)


def _app_from_layers(layers: dict[str, Any]) -> str | None:
    for layer_key in _APP_LAYER_PRIORITY:
        if layer_key in layers:
            return _normalize_app_token(layer_key)
    return None


def _app_from_stack(protocols: str | None) -> str | None:
    stack = _protocol_stack(protocols)
    for token in reversed(stack):
        if token in _STACK_SKIP_TOKENS:
            continue
        app = _normalize_app_token(token)
        if app:
            return app
    return None


def _app_from_ports(
    src_port: int | None,
    dst_port: int | None,
    transport_proto: str | None,
) -> str | None:
    """Guess application from well-known ports (tcp/udp only)."""
    if transport_proto not in ("tcp", "udp"):
        return None
    for port in (dst_port, src_port):
        if port is None:
            continue
        app = _WELL_KNOWN_PORTS.get(port)
        if app:
            return app
    return None


def _infer_packet_role(
    transport_proto: str | None,
    tcp_len: int | None,
    tcp_flags: Any,
) -> str:
    """
    Classify packets as control vs data.

    TCP: payload (tcp_len > 0) => data; zero-length => control (ACK/SYN/FIN/RST).
    UDP: data. ICMP/icmpv6: control. Other L4: other.
    """
    if transport_proto == "tcp":
        if tcp_len is not None and tcp_len > 0:
            return "data"
        return "control"
    if transport_proto == "udp":
        return "data"
    if transport_proto in ("icmp", "icmpv6"):
        return "control"
    return "other"


def _infer_app_proto(
    layers: dict[str, Any],
    protocols: str | None,
    *,
    transport_proto: str | None,
    src_port: int | None,
    dst_port: int | None,
) -> str | None:
    """
    Application protocol: dissector layer, then stack token, then port heuristic.
    """
    return (
        _app_from_layers(layers)
        or _app_from_stack(protocols)
        or _app_from_ports(src_port, dst_port, transport_proto)
    )


def parse_packet_record(record: dict[str, Any]) -> dict[str, Any]:
    """Map one tshark -T ek JSON object to a flat packet row."""
    layers = record.get("layers") or {}
    frame = _layer(layers, "frame")
    ip = _layer(layers, "ip")
    ipv6 = _layer(layers, "ipv6")
    tcp = _layer(layers, "tcp")
    udp = _layer(layers, "udp")
    icmp = _layer(layers, "icmp")

    protocols = frame.get("frame_frame_protocols")
    ip_proto = _to_int(ip.get("ip_ip_proto"))
    ipv6_nxt = _to_int(ipv6.get("ipv6_ipv6_nxt"))

    if ipv6:
        ip_version = 6
    elif ip:
        ip_version = 4
    else:
        ip_version = None

    ip_src = ip.get("ip_ip_src")
    ip_dst = ip.get("ip_ip_dst")
    ipv6_src = ipv6.get("ipv6_ipv6_src")
    ipv6_dst = ipv6.get("ipv6_ipv6_dst")
    src_host = ip_src or ipv6_src
    dst_host = ip_dst or ipv6_dst

    transport_proto = _infer_transport_proto(
        layers,
        protocols=protocols if isinstance(protocols, str) else None,
        ip_proto=ip_proto,
        ipv6_nxt=ipv6_nxt,
    )
    ip_proto_name = _proto_name(ip_proto if ip_version == 4 else ipv6_nxt)

    src_port = _to_int(
        _first_scalar(tcp.get("tcp_tcp_srcport") or udp.get("udp_udp_srcport"))
    )
    dst_port = _to_int(
        _first_scalar(tcp.get("tcp_tcp_dstport") or udp.get("udp_udp_dstport"))
    )
    app_proto = _infer_app_proto(
        layers,
        protocols if isinstance(protocols, str) else None,
        transport_proto=transport_proto,
        src_port=src_port,
        dst_port=dst_port,
    )
    tcp_len = _to_int(tcp.get("tcp_tcp_len"))
    packet_role = _infer_packet_role(transport_proto, tcp_len, tcp.get("tcp_tcp_flags"))

    return {
        "capture_timestamp_ms": _to_int(record.get("timestamp")),
        "frame_number": _to_int(frame.get("frame_frame_number")),
        "time_epoch": _to_float(frame.get("frame_frame_time_epoch")),
        "time_delta": _to_float(frame.get("frame_frame_time_delta")),
        "frame_len": _to_int(frame.get("frame_frame_len")),
        "protocols": protocols,
        "ip_version": ip_version,
        "ip_src": ip_src,
        "ip_dst": ip_dst,
        "ipv6_src": ipv6_src,
        "ipv6_dst": ipv6_dst,
        "src_host": src_host,
        "dst_host": dst_host,
        "ip_proto": ip_proto if ip_version == 4 else ipv6_nxt,
        "ip_proto_name": ip_proto_name,
        "ip_ttl": _to_int(ip.get("ip_ip_ttl") or ipv6.get("ipv6_ipv6_hlim")),
        "ip_len": _to_int(ip.get("ip_ip_len") or ipv6.get("ipv6_ipv6_plen")),
        "transport_proto": transport_proto,
        "l4_proto": transport_proto,
        "app_proto": app_proto,
        "src_port": src_port,
        "dst_port": dst_port,
        "tcp_stream": _to_int(tcp.get("tcp_tcp_stream")),
        "udp_stream": _to_int(udp.get("udp_udp_stream")),
        "tcp_len": tcp_len,
        "tcp_flags": tcp.get("tcp_tcp_flags"),
        "packet_role": packet_role,
        "tcp_time_delta": _to_float(tcp.get("tcp_tcp_time_delta")),
        "udp_time_delta": _to_float(udp.get("udp_udp_time_delta")),
        "icmp_type": _to_int(icmp.get("icmp_icmp_type")),
        "icmp_code": _to_int(icmp.get("icmp_icmp_code")),
    }


def iter_jsonl_packets(
    path: str | Path | None = None,
    *,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield parsed packet rows from a JSONL file."""
    jsonl_path = resolve_jsonl_path(path)
    count = 0
    with jsonl_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if "layers" not in record:
                continue
            yield parse_packet_record(record)
            count += 1
            if limit is not None and count >= limit:
                break


def load_raw_packets(
    path: str | Path | None = None,
    *,
    limit: int | None = None,
) -> pd.DataFrame:
    """Load packets without normalizing dtypes (all object/numeric mix)."""
    rows = list(iter_jsonl_packets(path, limit=limit))
    if not rows:
        return pd.DataFrame(columns=PACKET_COLUMNS)
    return pd.DataFrame(rows, columns=PACKET_COLUMNS)


def load_packets(
    path: str | Path | None = None,
    *,
    limit: int | None = None,
    sort: bool = True,
) -> pd.DataFrame:
    """
    Load JSONL into a packet-level DataFrame ready for analysis.

    Returns a DataFrame with PACKET_COLUMNS, sorted by frame_number by default.
    """
    df = load_raw_packets(path, limit=limit)
    if df.empty:
        return df

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
        "tcp_stream",
        "udp_stream",
        "tcp_len",
        "icmp_type",
        "icmp_code",
    ]
    float_cols = ["time_epoch", "time_delta", "tcp_time_delta", "udp_time_delta"]

    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if sort and "frame_number" in df.columns:
        df = df.sort_values("frame_number", kind="mergesort").reset_index(drop=True)

    return df


def _flow_id(row: pd.Series) -> str:
    proto = row.get("transport_proto") or row.get("l4_proto")
    if proto == "tcp" and pd.notna(row["tcp_stream"]):
        return f"tcp:{int(row['tcp_stream'])}"
    if proto == "udp" and pd.notna(row["udp_stream"]):
        return f"udp:{int(row['udp_stream'])}"
    return (
        f"5tuple:{row['src_host']}|{row['dst_host']}|{row['ip_proto']}|"
        f"{row['src_port']}|{row['dst_port']}"
    )


def elephant_byte_threshold(
    byte_sum: pd.Series,
    *,
    elephant_percentile: float = 95.0,
) -> float | None:
    """Byte-volume threshold separating mice from elephants (default: 95th percentile)."""
    sizes = pd.to_numeric(byte_sum, errors="coerce")
    positive = sizes[sizes > 0]
    if positive.empty:
        return None
    return float(np.percentile(positive, elephant_percentile))


def classify_flow_size_class(
    byte_sum: pd.Series,
    *,
    elephant_percentile: float = 95.0,
) -> pd.Series:
    """
    Split flows into mice vs elephant using a heavy-tail percentile threshold.

    Elephants are flows at or above the ``elephant_percentile`` of byte_sum
    (default top 5% at P95), matching the Pareto / heavy-tail convention in
    traffic characterization literature.

    Flows with non-positive byte_sum are labeled unknown.
    """
    sizes = pd.to_numeric(byte_sum, errors="coerce")
    positive = sizes[sizes > 0]
    if positive.empty:
        return pd.Series("unknown", index=byte_sum.index, dtype=object)
    threshold = float(np.percentile(positive, elephant_percentile))
    out = pd.Series("unknown", index=byte_sum.index, dtype=object)
    mask = sizes > 0
    out.loc[mask] = np.where(sizes.loc[mask] >= threshold, "elephant", "mice")
    return out


def load_flows(
    packets: pd.DataFrame | None = None,
    *,
    path: str | Path | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """
    Aggregate packet DataFrame into flow-level features.

    Uses Wireshark tcp/udp stream index when present; otherwise falls back to 5-tuple.
    """
    if packets is None:
        packets = load_packets(path, limit=limit)
    if packets.empty:
        return pd.DataFrame(columns=FLOW_COLUMNS)

    work = packets.copy()
    work["flow_id"] = work.apply(_flow_id, axis=1)

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
        lambda r: (r["byte_sum"] * 8 / r["duration"])
        if r["duration"] and r["duration"] > 0
        else pd.NA,
        axis=1,
    )
    flows["flow_size_class"] = classify_flow_size_class(flows["byte_sum"])
    return flows[FLOW_COLUMNS]


def summarize(packets: pd.DataFrame, flows: pd.DataFrame | None = None) -> dict[str, Any]:
    """Quick sanity-check stats after loading."""
    if flows is None:
        flows = load_flows(packets)
    by_transport = (
        packets["transport_proto"].value_counts(dropna=False).astype(int).to_dict()
    )
    by_app = packets["app_proto"].value_counts(dropna=False).astype(int).to_dict()
    return {
        "packets": len(packets),
        "flows": len(flows),
        "time_span_s": float(packets["time_epoch"].max() - packets["time_epoch"].min())
        if len(packets) > 1
        else 0.0,
        "by_transport_proto": by_transport,
        "by_app_proto": by_app,
        "unique_src_host": int(packets["src_host"].nunique(dropna=True)),
        "unique_dst_host": int(packets["dst_host"].nunique(dropna=True)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Load MAWI JSONL into packet and flow DataFrames."
    )
    parser.add_argument(
        "jsonl",
        nargs="?",
        default=None,
        help=f"Path to JSONL (default: {default_jsonl_path()})",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        help="Load only the first N packets",
    )
    args = parser.parse_args(argv)

    packets = load_packets(args.jsonl, limit=args.limit)
    flows = load_flows(packets)
    stats = summarize(packets, flows)

    print("packets:", stats["packets"])
    print("flows:", stats["flows"])
    print("time_span_s:", round(stats["time_span_s"], 6))
    print("by_transport_proto:", stats["by_transport_proto"])
    print("by_app_proto:", stats["by_app_proto"])
    print("unique_src_host:", stats["unique_src_host"])
    print("packet columns:", list(packets.columns))
    print(packets.head(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
