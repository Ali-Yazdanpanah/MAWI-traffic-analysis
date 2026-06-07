# Runbook — h2 tcpdump (Method 2)

**tcpdump** on host **h2** records raw frames to a pcap; telemetry is parsed offline from the in-band trailer.

## Summary

| Item | Value |
|------|-------|
| P4 export | In-band trailer on egress port 2 |
| Tap point | h2 NIC (`eth0`) |
| Output | `data/capture.pcap` → JSONL (parse step) |
| `make test-mawi` | `CAPTURE_MODE=pcap CAPTURE_SOURCE=h2` |

## Related files

| File | Role |
|------|------|
| `p4src/task2.p4` | In-band trailer |
| `control_plane/set_export_mode_thrift.py` / `set_export_mode_grpc.py` | Export mode |
| `scripts/test_mawi.sh` | Starts `tcpdump` on h2, then tcpreplay |
| `scripts/capture_on_h2.sh` | `CAPTURE_MODE=pcap` → `tcpdump` |
| `control_plane/capture_inband.py` | `--pcap` → JSONL |
| `control_plane/pipeline_capture_jsonl.py` | `--pcap` one-shot parse + plot |
| `control_plane/telemetry_decode.py` | Trailer decode |
| `control_plane/capture_jsonl_loader.py` | Frame parsing |

## Prerequisites

Same as [live-inband-sniff/runbook.md](../live-inband-sniff/runbook.md#prerequisites).

## Procedure (automated)

**Terminal A:** `make run-thrift` or `make run-grpc`

**Terminal B:**

```bash
cd /p4
sudo python3 control_plane/controller_grpc.py   # or controller_thrift.py

CAPTURE_MODE=pcap CAPTURE_SOURCE=h2 REPLAY_MULTIPLIER=0.001 make test-mawi
```

**Parse and plot:**

```bash
python3 control_plane/capture_inband.py --pcap data/capture.pcap -o data/capture.jsonl
python3 control_plane/pipeline_capture_jsonl.py --capture-jsonl data/capture.jsonl

# or single step:
python3 control_plane/pipeline_capture_jsonl.py --pcap data/capture.pcap -n 10000
```

## Procedure (manual, Mininet CLI)

```text
mininet> h2 tcpdump -i eth0 -s 0 -w /p4/data/capture.pcap -c 10000 &
mininet> h1 tcpreplay --multiplier=0.001 -i eth0 /p4/data/mawi_10000.pcap
```

After replay, stop tcpdump (`Ctrl+C` on h2 or `pkill tcpdump`), then parse as above.

## Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `CAPTURE_MODE` | — | Must be `pcap` |
| `CAPTURE_SOURCE` | — | Must be `h2` |
| `CAPTURE_PCAP` | `data/capture.pcap` | tcpdump output path |

## Verify success

```bash
tcpdump -r data/capture.pcap -c 3
python3 control_plane/capture_inband.py --pcap data/capture.pcap -n 5 -o /tmp/test.jsonl
wc -l /tmp/test.jsonl
```

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Empty or tiny pcap | tcpdump started **before** replay on h2 |
| `No telemetry-tagged packets` on parse | Wrong host pcap; need h2 egress with trailer |
| tcpdump won't stop after `test-mawi` | Script sends INT/TERM; run `h2 pkill tcpdump` |

## When to use

- Prefer a **pcap artifact** for debugging with Wireshark/tshark.
- Slightly heavier than live sniff (disk I/O + second parse pass).
