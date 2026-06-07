"""Parse the Task II telemetry_t trailer appended on BMv2 egress port 2."""

from __future__ import annotations

import struct
from typing import Any

TELEMETRY_SIZE = 32
_TELEMETRY_FMT = "!BB6sIII6s6s"

INT_COLLECTOR_PORT = 4790
INT_REPORT_MAGIC = 0x494E5431
INT_REPORT_MAGIC_BYTES = b"INT1"
INT_REPORT_SIZE = 54
_INT_REPORT_FMT = "!IBB6sIII6s6sIIBBHHI"


def u48(raw: bytes) -> int:
    return int.from_bytes(raw, byteorder="big", signed=False)


def unpack_telemetry(raw: bytes) -> dict[str, Any]:
    if len(raw) != TELEMETRY_SIZE:
        raise ValueError(f"telemetry trailer must be {TELEMETRY_SIZE} bytes, got {len(raw)}")
    flags, reserved, iat_raw, flow_id, pkt_count, byte_count, first_raw, last_raw = struct.unpack(
        _TELEMETRY_FMT, raw
    )
    iat_us = u48(iat_raw)
    return {
        "flags": flags,
        "reserved": reserved,
        "iat_valid": bool(flags & 0x01),
        "iat_us": iat_us,
        "iat_s": iat_us / 1_000_000.0,
        "p4_flow_id": flow_id,
        "flow_pkt_count": pkt_count,
        "flow_byte_count": byte_count,
        "flow_first_ts_us": u48(first_raw),
        "flow_last_ts_us": u48(last_raw),
    }


def split_telemetry(raw: bytes) -> tuple[bytes, dict[str, Any] | None]:
    """Return (frame_without_trailer, telemetry_dict) or (raw, None) if no trailer."""
    if len(raw) < TELEMETRY_SIZE:
        return raw, None
    tele_raw = raw[-TELEMETRY_SIZE:]
    payload = raw[:-TELEMETRY_SIZE]
    try:
        tele = unpack_telemetry(tele_raw)
    except (struct.error, ValueError):
        return raw, None
    return payload, tele


def unpack_int_report(payload: bytes) -> dict[str, Any]:
    """Parse a UDP INT report payload exported by task2.p4."""
    if len(payload) != INT_REPORT_SIZE:
        raise ValueError(f"INT report must be {INT_REPORT_SIZE} bytes, got {len(payload)}")
    (
        magic,
        flags,
        reserved,
        iat_raw,
        flow_id,
        pkt_count,
        byte_count,
        first_raw,
        last_raw,
        ipv4_src,
        ipv4_dst,
        ip_proto,
        ip_version,
        src_port,
        dst_port,
        l3_byte_len,
    ) = struct.unpack(_INT_REPORT_FMT, payload)
    if magic != INT_REPORT_MAGIC:
        raise ValueError(f"unexpected INT magic 0x{magic:08x}")
    iat_us = u48(iat_raw)
    return {
        "magic": magic,
        "flags": flags,
        "reserved": reserved,
        "iat_valid": bool(flags & 0x01),
        "iat_us": iat_us,
        "iat_s": iat_us / 1_000_000.0,
        "p4_flow_id": flow_id,
        "flow_pkt_count": pkt_count,
        "flow_byte_count": byte_count,
        "flow_first_ts_us": u48(first_raw),
        "flow_last_ts_us": u48(last_raw),
        "ipv4_src": ipv4_src,
        "ipv4_dst": ipv4_dst,
        "ip_proto": ip_proto,
        "ip_version": ip_version,
        "src_port": src_port,
        "dst_port": dst_port,
        "l3_byte_len": l3_byte_len,
    }
