# Runbook — UDP INT sniff (Method 4)

Out-of-band **UDP INT reports** to collector `10.0.0.2:4790`. Scapy on h2 sniffs UDP datagrams (not in-band trailers on forwarded traffic).

## Summary

| Item | Value |
|------|-------|
| P4 export | UDP INT clone → `10.0.0.2:4790` |
| Tap point | h2 NIC (`eth0`), UDP port 4790 |
| Output | `data/capture.jsonl` |
| `make test-mawi` | `CAPTURE_MODE=udp CAPTURE_USE_GRPC=1` |

## Related files

| File | Role |
|------|------|
| `p4src/task2.p4` | E2E clone + INT payload |
| `topo/task2-p4runtime.json` | Clone session 1 → port 2 |
| `control_plane/set_export_mode_grpc.py` | `--mode udp` (gRPC / `make run-grpc`) |
| `control_plane/set_export_mode_thrift.py` | `--mode udp` (Thrift / `make run-thrift`) |
| `control_plane/bmv2_grpc.py` / `bmv2_thrift.py` | Apply export mode + mirroring |
| `control_plane/capture_udp_int.py` | UDP sniff → JSONL |
| `control_plane/telemetry_decode.py` | INT payload unpack |
| `control_plane/capture_jsonl_loader.py` | `parse_int_report_record()` |
| `scripts/test_mawi.sh` | Configures export + starts `capture_udp_int.py` |
| `scripts/capture_on_h2.sh` | `CAPTURE_MODE=udp` |

## Prerequisites

1. Standard trace prep and `make build`.
2. **`make run-grpc`** recommended (UDP export + clone session via P4Runtime).
3. Rebuild after P4 changes: `make build`.

## Procedure (automated, gRPC)

**Terminal A:**

```bash
cd /p4
make run-grpc
```

**Terminal B:**

```bash
cd /p4
sudo python3 control_plane/controller_grpc.py

CAPTURE_MODE=udp CAPTURE_USE_GRPC=1 REPLAY_MULTIPLIER=0.001 make test-mawi
```

**Plot:**

```bash
python3 control_plane/pipeline_capture_jsonl.py --capture-jsonl data/capture.jsonl
```

## Procedure (Thrift)

```bash
make run-thrift
sudo python3 control_plane/controller_thrift.py
python3 control_plane/set_export_mode_thrift.py --mode udp

CAPTURE_MODE=udp REPLAY_MULTIPLIER=0.001 make test-mawi
```

## Procedure (manual)

```bash
# Before replay (container shell):
python3 control_plane/set_export_mode_grpc.py --mode udp
```

At `mininet>`:

```text
mininet> h2 python3 /p4/control_plane/capture_udp_int.py --interface eth0 -n 10000 --timeout 300 -o /p4/data/capture.jsonl &
mininet> h1 tcpreplay --multiplier=0.001 -i eth0 /p4/data/mawi_10000.pcap
```

## Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `CAPTURE_MODE` | — | Must be `udp` |
| `CAPTURE_SOURCE` | `h2` | UDP only works on h2 |
| `CAPTURE_USE_GRPC` | `0` | Set `1` with `make run-grpc` |
| `INT_UDP_PORT` | `4790` | Must match P4 `INT_COLLECTOR_PORT` |

## Verify success

```bash
wc -l data/capture.jsonl
head -1 data/capture.jsonl | python3 -m json.tool
# Records from INT path include telemetry fields from INT1 payload
```

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `No UDP INT reports received` | `set_export_mode_* --mode udp`; `make build` after P4 edits |
| Empty capture with `test-mawi` | `CAPTURE_USE_GRPC=1` when using `run-grpc` |
| Clone not working | `topo/task2-p4runtime.json` clone session; mirroring on Thrift path |

## Export mode `both`

To capture in-band **and** UDP INT, set `--mode both` and run collectors for each path (see [live-inband-sniff/runbook.md](../live-inband-sniff/runbook.md) + this runbook).

## When to use

- Homework comparison: out-of-band INT vs in-band trailer (Task III). Primary submission path uses live in-band capture; see [`../../../notebooks/task3_comparison.ipynb`](../../../notebooks/task3_comparison.ipynb).
- Forwarded packets on h2 have **no** in-band trailer when export is `udp` only.
