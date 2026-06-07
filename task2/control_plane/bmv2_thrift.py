"""BMv2 Thrift (simple_switch_CLI) helpers for register access."""

from __future__ import annotations

import re
import subprocess

NUM_FLOWS = 16384

GLOBAL_REGISTERS = (
    ("last_packet_timestamp", 0),
    ("last_ts_valid", 0),
)

FLOW_REGISTER_NAMES = (
    "flow_packet_count",
    "flow_byte_count",
    "flow_first_ts",
    "flow_last_ts",
)


def run_cli(thrift_port: int, commands: list[str]) -> str:
    proc = subprocess.run(
        ["simple_switch_CLI", "--thrift-port", str(thrift_port)],
        input="\n".join(commands) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"simple_switch_CLI exited {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout


def parse_register_value(line: str) -> int | None:
    match = re.search(r"=\s*(0x[0-9a-fA-F]+|\d+)", line)
    if not match:
        return None
    return int(match.group(1), 0)


def read_register(thrift_port: int, register_name: str, index: int) -> int:
    cmd = f"register_read MyIngress.{register_name} {index}"
    stdout = run_cli(thrift_port, [cmd])
    for line in stdout.splitlines():
        if register_name in line:
            value = parse_register_value(line)
            if value is not None:
                return value
    raise RuntimeError(f"Could not parse register read for {register_name}[{index}]:\n{stdout}")


def reset_telemetry_registers(thrift_port: int) -> None:
    commands = [
        "register_reset MyIngress.last_packet_timestamp",
        "register_reset MyIngress.last_ts_valid",
        "register_reset MyIngress.flow_packet_count",
        "register_reset MyIngress.flow_byte_count",
        "register_reset MyIngress.flow_first_ts",
        "register_reset MyIngress.flow_last_ts",
    ]
    run_cli(thrift_port, commands)


def configure_int_clone_session(
    thrift_port: int,
    *,
    session_id: int = 1,
    egress_port: int = 2,
) -> None:
    run_cli(thrift_port, [f"mirroring_add {session_id} {egress_port}"])


EXPORT_MODE_VALUES: dict[str, int] = {
    "inband": 0,
    "udp": 1,
    "both": 2,
}


def set_telemetry_export_mode(thrift_port: int, mode: str) -> None:
    mode_value = EXPORT_MODE_VALUES.get(mode)
    if mode_value is None:
        raise ValueError(f"unknown export mode {mode!r}; expected one of {sorted(EXPORT_MODE_VALUES)}")
    commands = [
        "table_clear MyIngress.configure_export_mode",
        f"table_add MyIngress.configure_export_mode MyIngress.set_export_mode 1 => {mode_value}",
    ]
    run_cli(thrift_port, commands)
    if mode in ("udp", "both"):
        configure_int_clone_session(thrift_port)


def read_global_state(thrift_port: int) -> dict:
    state = {}
    for name, index in GLOBAL_REGISTERS:
        state[name] = read_register(thrift_port, name, index)
    state["global_iat_ready"] = bool(state["last_ts_valid"])
    state["last_packet_timestamp_us"] = state["last_packet_timestamp"]
    return state


def read_active_flows(
    thrift_port: int,
    *,
    max_flows: int,
    min_packets: int,
) -> list[dict]:
    flows: list[dict] = []
    limit = min(max_flows, NUM_FLOWS)
    for flow_id in range(limit):
        pkt_count = read_register(thrift_port, "flow_packet_count", flow_id)
        if pkt_count < min_packets:
            continue
        byte_count = read_register(thrift_port, "flow_byte_count", flow_id)
        first_ts = read_register(thrift_port, "flow_first_ts", flow_id)
        last_ts = read_register(thrift_port, "flow_last_ts", flow_id)
        duration_us = max(last_ts - first_ts, 0)
        duration_s = duration_us / 1_000_000.0 if duration_us else 0.0
        throughput_bps = (byte_count * 8.0 / duration_s) if duration_s > 0 else 0.0
        flows.append(
            {
                "flow_id": f"p4:{flow_id}",
                "p4_flow_id": flow_id,
                "packet_count": pkt_count,
                "byte_sum": byte_count,
                "start_epoch": first_ts / 1_000_000.0,
                "end_epoch": last_ts / 1_000_000.0,
                "duration": duration_s,
                "throughput_bps": throughput_bps,
            }
        )
    return flows
