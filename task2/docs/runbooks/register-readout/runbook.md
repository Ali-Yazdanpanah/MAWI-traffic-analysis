# Runbook — Register readout (Method 5)

Read **aggregate** flow register state from the switch control plane. This is **not** per-packet capture — use Methods 1–4 for IAT and distribution plots.

## Summary

| Item | Thrift (`make run-thrift`) | gRPC (`make run-grpc`) |
|------|---------------------|------------------------|
| API | Thrift **9090** | P4Runtime **50051** |
| Script | `read_registers_thrift.py` | `read_registers_grpc.py` |
| Reset | `controller_thrift.py` | `controller_grpc.py` (pipeline reload) |
| Output | `data/registers.json` | `data/registers_grpc.json` |

## Related files

| File | Role |
|------|------|
| `control_plane/bmv2_thrift.py` | `simple_switch_CLI` register read |
| `control_plane/bmv2_grpc.py` | P4Runtime register read |
| `control_plane/read_registers_thrift.py` | Thrift dump CLI |
| `control_plane/read_registers_grpc.py` | gRPC dump CLI |
| `control_plane/controller_thrift.py` | Thrift register reset |
| `control_plane/controller_grpc.py` | gRPC pipeline reload reset |
| `control_plane/pipeline_capture_jsonl.py` | Optional `--dump-registers` after capture |
| `p4src/task2.p4` | Register definitions |
| `Makefile` | `make read-registers`, `make read-registers-grpc`, `make reset`, `make reset-grpc` |

## Prerequisites

1. Mininet running with telemetry already processed (after MAWI replay), **or** you only need post-replay snapshot.
2. Pick **one** API — do not mix Thrift tools with `simple_switch_grpc` or vice versa.

## Procedure (Thrift)

```bash
cd /p4
make run-thrift                    # terminal A

# terminal B — after replay:
sudo python3 control_plane/controller_thrift.py    # reset before replay
# ... run capture / replay ...

python3 control_plane/read_registers_thrift.py \
  --max-flows 16384 \
  -o data/registers.json

# or:
make read-registers
```

## Procedure (gRPC)

```bash
cd /p4
make run-grpc               # terminal A

# terminal B — after replay:
sudo python3 control_plane/controller_grpc.py
# or: make reset-grpc

python3 control_plane/read_registers_grpc.py \
  --max-flows 16384 \
  -o data/registers_grpc.json

# or:
make read-registers-grpc
```

## Combined with packet capture

After a JSONL capture from Methods 1–4:

```bash
# Thrift switch:
python3 control_plane/pipeline_capture_jsonl.py \
  --capture-jsonl data/capture.jsonl \
  --dump-registers data/registers.json

# gRPC switch:
python3 control_plane/pipeline_capture_jsonl.py \
  --capture-jsonl data/capture.jsonl \
  --use-grpc \
  --dump-registers data/registers_grpc.json
```

## Verify success

```bash
python3 -m json.tool data/registers_grpc.json | head -40
```

JSON includes `global` (e.g. `last_packet_timestamp`) and `active_flows` (per slot totals).

## Limitations

| Topic | Detail |
|-------|--------|
| Per-packet IAT | **Not available** — registers hold aggregates per flow slot |
| gRPC register **writes** | Unreliable on BMv2 ([PI#376](https://github.com/p4lang/PI/issues/376)); reset uses pipeline reload |
| Hash collisions | `flow_id = CRC16(5-tuple) mod 16384` — discuss in Task III |
| Byte counts | L3 length in switch vs L2 `frame_len` in Task I |

## Troubleshooting

| Symptom | Check |
|---------|--------|
| gRPC connection refused | `make run-grpc`; `ss -tln \| grep 50051` |
| Thrift CLI not found | Run inside Docker; `make run-thrift` not `run-grpc` |
| gRPC read fails | Use `read_registers_grpc.py` only — **no** Thrift fallback |
| Stale counters | Reset before replay (`controller_*.py`) |

## When to use

- Task III: compare flow-level totals vs Task I / vs JSONL capture (see [`../../../notebooks/task3_comparison.ipynb`](../../../notebooks/task3_comparison.ipynb)).
- Sanity-check switch state after replay.
- **Always** pair with a packet capture method for distribution plots.
