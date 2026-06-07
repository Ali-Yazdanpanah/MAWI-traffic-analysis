"""Push BMv2 forwarding pipeline via P4Runtime (SetForwardingPipelineConfig)."""

from __future__ import annotations

import json
from pathlib import Path

import google.protobuf.text_format
from p4.config.v1 import p4info_pb2
from p4.v1 import p4runtime_pb2

from .bmv2 import Bmv2SwitchConnection


def _resolve_path(workdir: Path, configured: str) -> Path:
    path = Path(configured)
    if not path.is_absolute():
        path = workdir / path
    return path.resolve()


def load_runtime_paths(runtime_json: str | Path, *, workdir: str | Path | None = None) -> tuple[Path, Path]:
    runtime_path = Path(runtime_json).resolve()
    base = Path(workdir).resolve() if workdir is not None else runtime_path.parent
    with runtime_path.open(encoding="utf-8") as handle:
        conf = json.load(handle)
    if conf.get("target") != "bmv2":
        raise ValueError(f"Unsupported P4Runtime target: {conf.get('target')!r}")
    p4info_path = _resolve_path(base, conf["p4info"])
    bmv2_json_path = _resolve_path(base, conf["bmv2_json"])
    if not p4info_path.is_file():
        raise FileNotFoundError(f"P4Info not found: {p4info_path}")
    if not bmv2_json_path.is_file():
        raise FileNotFoundError(f"BMv2 JSON not found: {bmv2_json_path}")
    return p4info_path, bmv2_json_path


def build_set_pipeline_request(
    *,
    device_id: int,
    p4info_path: str | Path,
    bmv2_json_path: str | Path,
) -> p4runtime_pb2.SetForwardingPipelineConfigRequest:
    p4info_path = Path(p4info_path)
    bmv2_json_path = Path(bmv2_json_path)
    json_bytes = bmv2_json_path.read_bytes()
    if len(json_bytes) < 100:
        raise RuntimeError(
            f"BMv2 JSON looks invalid ({len(json_bytes)} bytes): {bmv2_json_path}"
        )

    p4info = p4info_pb2.P4Info()
    google.protobuf.text_format.Merge(
        p4info_path.read_text(encoding="utf-8"),
        p4info,
        allow_unknown_field=True,
    )
    if not p4info.registers:
        raise RuntimeError(f"P4Info merge failed or empty registers: {p4info_path}")

    json.loads(json_bytes.decode("utf-8"))

    request = p4runtime_pb2.SetForwardingPipelineConfigRequest()
    request.device_id = device_id
    request.election_id.high = 0
    request.election_id.low = 1
    request.config.p4info.CopyFrom(p4info)
    # BMv2 simple_switch_grpc accepts raw compiled JSON here (see base_test.cpp).
    # Do not wrap in p4.tmp.P4DeviceConfig unless field numbers match PI exactly.
    request.config.p4_device_config = json_bytes
    request.action = p4runtime_pb2.SetForwardingPipelineConfigRequest.VERIFY_AND_COMMIT
    return request


def push_forwarding_pipeline(
    *,
    grpc_addr: str,
    device_id: int,
    p4info_path: str | Path,
    bmv2_json_path: str | Path,
    proto_dump_file: str | None = None,
) -> None:
    """Load p4info + BMv2 JSON into simple_switch_grpc via P4Runtime."""
    request = build_set_pipeline_request(
        device_id=device_id,
        p4info_path=p4info_path,
        bmv2_json_path=bmv2_json_path,
    )

    sw = Bmv2SwitchConnection(
        address=grpc_addr,
        device_id=device_id,
        proto_dump_file=proto_dump_file,
    )
    try:
        sw.MasterArbitrationUpdate()
        sw.client_stub.SetForwardingPipelineConfig(request)
    finally:
        sw.shutdown()


def push_from_runtime_json(
    *,
    grpc_addr: str,
    device_id: int,
    runtime_json: str | Path,
    workdir: str | Path | None = None,
    proto_dump_file: str | None = None,
) -> None:
    p4info_path, bmv2_json_path = load_runtime_paths(runtime_json, workdir=workdir)
    push_forwarding_pipeline(
        grpc_addr=grpc_addr,
        device_id=device_id,
        p4info_path=p4info_path,
        bmv2_json_path=bmv2_json_path,
        proto_dump_file=proto_dump_file,
    )
