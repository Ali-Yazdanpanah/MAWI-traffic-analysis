"""BMv2 P4Runtime (gRPC) helpers for Task II register access."""

from __future__ import annotations

import sys
from pathlib import Path

from p4.v1 import p4runtime_pb2

try:
    from p4.v1 import p4data_pb2
except ImportError:  # older p4runtime bundles
    p4data_pb2 = p4runtime_pb2  # type: ignore[misc, assignment]

from paths import task2_root

NUM_FLOWS = 16384
DEFAULT_GRPC_ADDR = "127.0.0.1:50051"
DEFAULT_DEVICE_ID = 0
DEFAULT_RUNTIME_JSON = task2_root() / "topo" / "task2-p4runtime.json"

GLOBAL_REGISTERS: tuple[tuple[str, int], ...] = (
    ("MyIngress.last_packet_timestamp", 0),
    ("MyIngress.last_ts_valid", 0),
)

FLOW_REGISTER_NAMES: tuple[str, ...] = (
    "MyIngress.flow_packet_count",
    "MyIngress.flow_byte_count",
    "MyIngress.flow_first_ts",
    "MyIngress.flow_last_ts",
)

_UTILS = task2_root() / "utils"
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

from p4runtime_lib.bmv2 import Bmv2SwitchConnection  # noqa: E402
from p4runtime_lib.convert import decodeNum, encode  # noqa: E402
from p4runtime_lib.helper import P4InfoHelper  # noqa: E402
from p4runtime_lib.pipeline_config import (  # noqa: E402
    build_set_pipeline_request,
    push_from_runtime_json,
)


def default_p4info_path() -> Path:
    return task2_root() / "build" / "task2.p4.p4info.txtpb"


def default_bmv2_json_path() -> Path:
    return task2_root() / "build" / "task2.json"


def _decode_register_data(data_msg) -> int:
    """Decode register payload from P4Data (new API) or raw bytes (legacy)."""
    if hasattr(data_msg, "bitstring") and data_msg.bitstring:
        return decodeNum(data_msg.bitstring)
    if isinstance(data_msg, (bytes, bytearray)):
        return decodeNum(data_msg)
    raise RuntimeError("RegisterEntry has no decodable P4Data payload")


def _build_register_entry(register_id: int, index: int, value: int, bitwidth: int) -> p4runtime_pb2.RegisterEntry:
    """Build a standalone RegisterEntry (P4Runtime wraps payload in P4Data)."""
    entry = p4runtime_pb2.RegisterEntry()
    entry.register_id = register_id
    entry.index.index = index
    payload = p4data_pb2.P4Data()
    payload.bitstring = encode(value, bitwidth)
    entry.data.CopyFrom(payload)
    return entry


def _add_register_modify(
    request: p4runtime_pb2.WriteRequest,
    *,
    register_id: int,
    index: int,
    value: int,
    bitwidth: int,
) -> None:
    update = request.updates.add()
    update.type = p4runtime_pb2.Update.MODIFY
    update.entity.register_entry.CopyFrom(
        _build_register_entry(register_id, index, value, bitwidth)
    )


class Bmv2GrpcClient:
    """P4Runtime client for task2 register read/write."""

    def __init__(
        self,
        *,
        grpc_addr: str = DEFAULT_GRPC_ADDR,
        device_id: int = DEFAULT_DEVICE_ID,
        p4info_path: Path | str | None = None,
        load_pipeline: bool = False,
    ) -> None:
        self.grpc_addr = grpc_addr
        self.device_id = device_id
        p4info = Path(p4info_path) if p4info_path is not None else default_p4info_path()
        if not p4info.is_file():
            raise FileNotFoundError(f"P4Info not found: {p4info} (run make build)")
        self.p4info = P4InfoHelper(str(p4info))
        self._sw = Bmv2SwitchConnection(name="task2", address=grpc_addr, device_id=device_id)
        self._stub = self._sw.client_stub
        self._sw.MasterArbitrationUpdate()
        if load_pipeline:
            bmv2_json = default_bmv2_json_path()
            if not bmv2_json.is_file():
                raise FileNotFoundError(f"BMv2 JSON not found: {bmv2_json} (run make build)")
            pipeline_request = build_set_pipeline_request(
                device_id=device_id,
                p4info_path=p4info,
                bmv2_json_path=bmv2_json,
            )
            self._stub.SetForwardingPipelineConfig(pipeline_request)

    def close(self) -> None:
        self._sw.shutdown()

    def __enter__(self) -> Bmv2GrpcClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _register_bitwidth(self, register_name: str) -> int:
        reg = self.p4info.get("registers", name=register_name)
        bit_spec = reg.type_spec.bitstring.bit
        # p4info proto: `bit` is a single P4BitTypeSpec in current p4c builds,
        # but older generated code treated it as a repeated field.
        if hasattr(bit_spec, "bitwidth"):
            return int(bit_spec.bitwidth)
        return int(bit_spec[0].bitwidth)

    def _register_id(self, register_name: str) -> int:
        return self.p4info.get_registers_id(register_name)

    def _set_election_id(self, request) -> None:
        if hasattr(request, "election_id"):
            request.election_id.high = 0
            request.election_id.low = 1

    def reload_forwarding_pipeline(self) -> None:
        """Reload BMv2 JSON via P4Runtime (clears registers and pipeline state)."""
        pipeline_request = build_set_pipeline_request(
            device_id=self.device_id,
            p4info_path=default_p4info_path(),
            bmv2_json_path=default_bmv2_json_path(),
        )
        self._stub.SetForwardingPipelineConfig(pipeline_request)

    def read_register(self, register_name: str, index: int) -> int:
        register_id = self._register_id(register_name)
        request = p4runtime_pb2.ReadRequest()
        request.device_id = self.device_id
        self._set_election_id(request)
        entry = request.entities.add().register_entry
        entry.register_id = register_id
        entry.index.index = index
        for response in self._stub.Read(request):
            for entity in response.entities:
                return _decode_register_data(entity.register_entry.data)
        raise RuntimeError(f"No P4Runtime data for {register_name}[{index}]")

    def read_register_all(self, register_name: str) -> dict[int, int]:
        register_id = self._register_id(register_name)
        request = p4runtime_pb2.ReadRequest()
        request.device_id = self.device_id
        self._set_election_id(request)
        request.entities.add().register_entry.register_id = register_id
        values: dict[int, int] = {}
        for response in self._stub.Read(request):
            for entity in response.entities:
                entry = entity.register_entry
                values[int(entry.index.index)] = _decode_register_data(entry.data)
        return values

    def write_register(self, register_name: str, index: int, value: int) -> None:
        register_id = self._register_id(register_name)
        bitwidth = self._register_bitwidth(register_name)
        request = p4runtime_pb2.WriteRequest()
        request.device_id = self.device_id
        self._set_election_id(request)
        _add_register_modify(
            request,
            register_id=register_id,
            index=index,
            value=value,
            bitwidth=bitwidth,
        )
        self._stub.Write(request)

    def reset_telemetry_registers(self, *, batch_size: int = 256) -> None:
        # BMv2 simple_switch_grpc has no working P4Runtime register Write API (PI#376).
        # Reloading the compiled pipeline resets register arrays to their initial values.
        del batch_size
        self.reload_forwarding_pipeline()

    def read_global_state(self) -> dict[str, int | bool]:
        last_ts = self.read_register("MyIngress.last_packet_timestamp", 0)
        ts_valid = self.read_register("MyIngress.last_ts_valid", 0)
        return {
            "last_packet_timestamp": last_ts,
            "last_ts_valid": ts_valid,
            "global_iat_ready": bool(ts_valid),
            "last_packet_timestamp_us": last_ts,
        }

    def read_active_flows(
        self,
        *,
        max_flows: int = NUM_FLOWS,
        min_packets: int = 1,
    ) -> list[dict[str, float | int | str]]:
        limit = min(max_flows, NUM_FLOWS)
        pkt_counts = self.read_register_all("MyIngress.flow_packet_count")
        byte_counts = self.read_register_all("MyIngress.flow_byte_count")
        first_ts = self.read_register_all("MyIngress.flow_first_ts")
        last_ts_map = self.read_register_all("MyIngress.flow_last_ts")

        flows: list[dict[str, float | int | str]] = []
        for flow_id in range(limit):
            pkt_count = pkt_counts.get(flow_id, 0)
            if pkt_count < min_packets:
                continue
            byte_count = byte_counts.get(flow_id, 0)
            first = first_ts.get(flow_id, 0)
            last = last_ts_map.get(flow_id, 0)
            duration_us = max(last - first, 0)
            duration_s = duration_us / 1_000_000.0 if duration_us else 0.0
            throughput_bps = (byte_count * 8.0 / duration_s) if duration_s > 0 else 0.0
            flows.append(
                {
                    "flow_id": f"p4:{flow_id}",
                    "p4_flow_id": flow_id,
                    "packet_count": pkt_count,
                    "byte_sum": byte_count,
                    "start_epoch": first / 1_000_000.0,
                    "end_epoch": last / 1_000_000.0,
                    "duration": duration_s,
                    "throughput_bps": throughput_bps,
                }
            )
        return flows

    def configure_int_clone_session(self, *, session_id: int = 1, egress_port: int = 2) -> None:
        clone_entry = self.p4info.buildCloneSessionEntry(
            session_id,
            [{"egress_port": egress_port, "instance": 1}],
        )
        self._sw.WritePREEntry(clone_entry)

    def set_telemetry_export_mode(self, mode: str) -> None:
        action_map = {
            "inband": "MyIngress.set_export_inband",
            "udp": "MyIngress.set_export_udp",
            "both": "MyIngress.set_export_both",
        }
        if mode not in action_map:
            raise ValueError(f"unknown export mode {mode!r}; expected one of {sorted(action_map)}")
        table_entry = self.p4info.buildTableEntry(
            table_name="MyIngress.configure_export_mode",
            match_fields={"standard_metadata.ingress_port": 1},
            action_name=action_map[mode],
        )
        self._sw.WriteTableEntry(table_entry)
        if mode in ("udp", "both"):
            self.configure_int_clone_session()


def reset_telemetry_registers(
    grpc_addr: str = DEFAULT_GRPC_ADDR,
    *,
    device_id: int = DEFAULT_DEVICE_ID,
    p4info_path: Path | str | None = None,
    runtime_json: Path | str | None = None,
) -> None:
    """Reset telemetry state by reloading the P4 pipeline over P4Runtime."""
    del p4info_path  # runtime_json references build artifacts
    push_from_runtime_json(
        grpc_addr=grpc_addr,
        device_id=device_id,
        runtime_json=runtime_json or DEFAULT_RUNTIME_JSON,
        workdir=task2_root(),
    )


def read_global_state(
    grpc_addr: str = DEFAULT_GRPC_ADDR,
    *,
    device_id: int = DEFAULT_DEVICE_ID,
    p4info_path: Path | str | None = None,
) -> dict:
    with Bmv2GrpcClient(
        grpc_addr=grpc_addr,
        device_id=device_id,
        p4info_path=p4info_path,
    ) as client:
        return client.read_global_state()


def read_active_flows(
    grpc_addr: str = DEFAULT_GRPC_ADDR,
    *,
    device_id: int = DEFAULT_DEVICE_ID,
    max_flows: int = NUM_FLOWS,
    min_packets: int = 1,
    p4info_path: Path | str | None = None,
) -> list[dict]:
    with Bmv2GrpcClient(
        grpc_addr=grpc_addr,
        device_id=device_id,
        p4info_path=p4info_path,
    ) as client:
        return client.read_active_flows(max_flows=max_flows, min_packets=min_packets)


def set_telemetry_export_mode(
    mode: str,
    grpc_addr: str = DEFAULT_GRPC_ADDR,
    *,
    device_id: int = DEFAULT_DEVICE_ID,
    p4info_path: Path | str | None = None,
) -> None:
    with Bmv2GrpcClient(
        grpc_addr=grpc_addr,
        device_id=device_id,
        p4info_path=p4info_path,
    ) as client:
        client.set_telemetry_export_mode(mode)
