# Runbook — Switch port pcap (Method 3)

BMv2 writes **all traffic on switch port 2** to `pcaps/s1-eth2.pcap` automatically. No collector process on h2.

## Summary

| Item | Value |
|------|-------|
| P4 export | In-band trailer on egress port 2 |
| Tap point | BMv2 port 2 (toward h2) |
| Output | `pcaps/s1-eth2.pcap` |
| `make test-mawi` | `CAPTURE_MODE=switch` or `CAPTURE_SOURCE=switch` |

## Related files

| File | Role |
|------|------|
| `utils/run_exercise.py` | Launches BMv2 with `--pcap` |
| `utils/p4_mininet.py` | Switch / pcap path setup |
| `p4src/task2.p4` | In-band trailer |
| `scripts/test_mawi.sh` | Replay only (no h2 collector) |
| `control_plane/capture_inband.py` | Parse switch pcap → JSONL |
| `control_plane/pipeline_capture_jsonl.py` | `--pcap pcaps/s1-eth2.pcap` |
| `Makefile` | `SWITCH_PCAP` (default `pcaps/s1-eth2_out.pcap`; legacy `s1-eth2.pcap` also works) |

## Prerequisites

Same as [live-inband-sniff/runbook.md](../live-inband-sniff/runbook.md#prerequisites).

Mininet must be started with **`make run-thrift`** or **`make run-grpc`** (BMv2 `--pcap` is enabled by default).

## Procedure (automated)

**Terminal A:** `make run-grpc` (or `make run-thrift`)

**Terminal B:**

```bash
cd /p4
sudo python3 control_plane/controller_grpc.py

CAPTURE_MODE=switch REPLAY_MULTIPLIER=0.001 make test-mawi
# equivalent:
# CAPTURE_MODE=pcap CAPTURE_SOURCE=switch REPLAY_MULTIPLIER=0.001 make test-mawi
```

**Parse and plot** (use `-n` to limit — pcap covers the whole Mininet session):

```bash
python3 control_plane/pipeline_capture_jsonl.py --pcap pcaps/s1-eth2.pcap -n 10000
```

## Procedure (manual)

1. Start Mininet (`make run-thrift`).
2. Reset registers (`controller_thrift.py` or `controller_grpc.py`).
3. Replay on h1 only — no h2 capture:

```text
mininet> h1 tcpreplay --multiplier=0.001 -i eth0 /p4/data/mawi_10000.pcap
```

4. Parse from container shell:

```bash
python3 control_plane/capture_inband.py --pcap pcaps/s1-eth2.pcap -n 10000 -o data/capture.jsonl
python3 control_plane/plot_capture_jsonl.py data/capture.jsonl
```

## Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `CAPTURE_MODE` | — | `switch` or `pcap` with `CAPTURE_SOURCE=switch` |
| `SWITCH_PCAP` | `pcaps/s1-eth2_out.pcap` | **Port 2** egress only (not `s1-eth1.pcap`) |

## Verify success

```bash
ls -la pcaps/s1-eth2.pcap
python3 -c "
from scapy.utils import PcapReader
print(sum(1 for _ in PcapReader('pcaps/s1-eth2.pcap')))
"
```

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Pcap missing | First packet must traverse port 2; restart `make run-thrift` |
| Too many / wrong frames | Pcap includes full session; filter with `-n` when parsing |
| No telemetry in pcap | Export mode must be in-band; use port **2** file |

## When to use

- No Scapy/tcpdump process on h2.
- Good for verifying what the switch actually emits on the wire.
