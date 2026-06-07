# Runbook — Live in-band sniff (Method 1)

**Default homework path.** Scapy on host **h2** parses the 32-byte in-band telemetry trailer on the wire and writes JSONL directly.

## Summary

| Item | Value |
|------|-------|
| P4 export | In-band trailer on egress port 2 |
| Tap point | h2 NIC (`eth0`) |
| Output | `data/capture.jsonl` |
| `make test-mawi` | `CAPTURE_MODE=live CAPTURE_SOURCE=h2` (defaults) |

## Related files

| File | Role |
|------|------|
| `p4src/task2.p4` | Appends `telemetry_t` trailer |
| `control_plane/set_export_mode_thrift.py` | Export mode via Thrift (`make run-thrift`) |
| `control_plane/set_export_mode_grpc.py` | Export mode via gRPC (`make run-grpc`) |
| `control_plane/capture_inband.py` | `--interface` live sniff → JSONL |
| `control_plane/telemetry_decode.py` | Trailer unpack |
| `control_plane/capture_jsonl_loader.py` | Frame → record dict |
| `scripts/test_mawi.sh` | Automated replay + capture |
| `scripts/capture_on_h2.sh` | Mininet helper (`CAPTURE_MODE=live`) |
| `scripts/replay_on_h1.sh` | tcpreplay wrapper |

## Prerequisites

1. `201302011400.dump.gz` at repo root (`/repo/201302011400.dump.gz` in Docker).
2. `make trace-prepare` → `data/mawi_10000.pcap` (first 10,000 frames; same packet head as Task I at `-n 10000`).
3. `make build` → `build/task2.json`.
4. Mininet running: `make run-thrift` or `make run-grpc`.

## Procedure (automated)

**Terminal A** — Mininet:

```bash
cd /p4
make run-grpc    # or: make run-thrift
```

**Terminal B** — reset, capture, replay:

```bash
docker exec -it task2-p4-env bash
cd /p4

# gRPC reset (make run-grpc):
sudo python3 control_plane/controller_grpc.py

# Thrift reset (make run-thrift):
# sudo python3 control_plane/controller_thrift.py

REPLAY_MULTIPLIER=0.001 make test-mawi
# equivalent:
# CAPTURE_MODE=live CAPTURE_SOURCE=h2 REPLAY_MULTIPLIER=0.001 make test-mawi
```

**Plot:**

```bash
python3 control_plane/pipeline_capture_jsonl.py --capture-jsonl data/capture.jsonl
# or:
python3 control_plane/plot_capture_jsonl.py data/capture.jsonl -n 10000
```

## Procedure (manual, Mininet CLI)

At `mininet>`:

```text
mininet> h2 python3 /p4/control_plane/capture_inband.py --interface eth0 -n 10000 --timeout 300 -o /p4/data/capture.jsonl &
mininet> h1 tcpreplay --multiplier=0.001 -i eth0 /p4/data/mawi_10000.pcap
```

Or use the helper:

```text
mininet> h2 sh /p4/scripts/capture_on_h2.sh /p4/data/capture.jsonl 10000 eth0 &
mininet> h1 tcpreplay --multiplier=0.001 -i eth0 /p4/data/mawi_10000.pcap
```

## Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `CAPTURE_MODE` | `live` | Must be `live` |
| `CAPTURE_SOURCE` | `h2` | Must be `h2` |
| `CAPTURE_TIMEOUT` | `300` | Sniff timeout (seconds) |
| `PACKET_LIMIT` | `10000` | Target record count |
| `REPLAY_MULTIPLIER` | `0.001` | Lower (e.g. `0.0001`) if BMv2 drops packets |
| `CAPTURE_USE_GRPC` | `0` | Set `1` with `make run-grpc` for export-mode config |

## Verify success

```bash
wc -l data/capture.jsonl          # expect ~PACKET_LIMIT
head -1 data/capture.jsonl | python3 -m json.tool
```

Records should include `p4_iat_us`, `p4_flow_id`, `p4_flow_pkt_count`, etc.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| `No telemetry-tagged packets` | Capture on **h2**, not h1; export mode is in-band |
| Fewer records than expected | Lower `REPLAY_MULTIPLIER`; increase `CAPTURE_TIMEOUT` |
| Collector hangs | Replay finished? Stop sniff or wait for timeout |
| Garbage flow counters | Reset registers before replay (`controller_*.py`) |

## Not for per-packet plots alone

Register readout (`register-readout/runbook.md`) gives flow totals only — use this method (or another JSONL/pcap capture) for distributions.
