# Task II — Run with MAWI trace in Docker

For a full comparison of **export** (P4: in-band / UDP / both) vs **collection** (h2 sniff, tcpdump, switch pcap, register read), see [Getting telemetry out of the data plane](../README.md#getting-telemetry-out-of-the-data-plane) in `task2/README.md`.

**Step-by-step runbooks** (one per capture method): [runbooks/README.md](runbooks/README.md)

**Trace alignment with Task I:** `make trace-prepare` writes `data/mawi_10000.pcap` (first 10,000 frames from `201302011400`). Task I should use the same head of the capture (`plot_analysis … -n 10000` on JSONL exported in file order). Task III comparison: [`../../notebooks/task3_comparison.ipynb`](../../notebooks/task3_comparison.ipynb).

## Which file is which?

| File | Use |
|------|-----|
| `201302011400.dump.gz` | **Replay into BMv2** (decompress to PCAP) |
| `201302011400.csv` | **Task I only** (flattened tshark export; not injectable) |
| `201302011400.jsonl` | **Task I only** (software analysis) |

Download the dump if missing:

```text
http://mawi.wide.ad.jp/mawi/samplepoint-F/2013/201302011400.dump.gz
```

Place **`201302011400.dump.gz`** at the **repo root** (sibling of `task2/`). Inside Docker it appears as `/repo/201302011400.dump.gz`.

Quick prep (from container):

```bash
cd /p4
make trace-prepare          # or: PACKET_LIMIT=10000 ./scripts/prepare_trace.sh
# -> data/mawi_10000.pcap and data/replay.pcap (symlink)
```

## Thrift vs gRPC switch

| Command | Binary | Register access |
|---------|--------|-----------------|
| **`make run-thrift`** (default) | `simple_switch` | Thrift **9090** — `controller_thrift.py`, `read_registers_thrift.py` |
| **`make run-grpc`** (homework) | `simple_switch_grpc` | P4Runtime gRPC **50051** — pipeline load + reset via `controller_grpc.py` |

After `make run-thrift`, verify: `ss -tln | grep 9090`  
After `make run-grpc`, verify: `ss -tln | grep 50051`

### gRPC workflow (matches homework PDF)

Terminal A:

```bash
make build
make run-grpc
```

Terminal B — reset and replay (same capture/replay steps as below), then:

```bash
sudo python3 control_plane/controller_grpc.py
# Resets telemetry by reloading the P4 pipeline over P4Runtime (BMv2 has no register Write API).
# or: make reset-grpc

REPLAY_MULTIPLIER=0.001 make test-mawi
# Live Scapy sniff on h2 -> data/capture.jsonl (default). Legacy tcpdump: CAPTURE_MODE=pcap make test-mawi

python3 control_plane/read_registers_grpc.py -o data/registers_grpc.json
# or: make read-registers-grpc

python3 control_plane/pipeline_capture_jsonl.py \
  --capture-jsonl data/capture.jsonl \
  --use-grpc \
  --dump-registers data/registers_grpc.json
```

## 1. Start Docker

From the host (PowerShell / bash):

```bash
cd task2
docker compose build
docker compose up -d
docker exec -it task2-p4-env bash
cd /p4
# Python deps (scipy, pandas, …) are installed by the Docker image / entrypoint.
```

Inside the container, `/p4` = `task2/`, `/repo` = repo root (read-only).

## 2. Prepare PCAP subset

```bash
chmod +x scripts/prepare_trace.sh
PACKET_LIMIT=10000 ./scripts/prepare_trace.sh
# -> /p4/data/mawi_10000.pcap
```

## 3. Build P4 and start Mininet (terminal A)

```bash
cd /p4
make build
make run-thrift
```

You should get a `mininet>` prompt. Leave this open.

## 4. Reset registers (terminal B)

Open a **second** shell into the same container:

```bash
docker exec -it task2-p4-env bash
cd /p4
sudo python3 control_plane/controller_thrift.py
```

## 5. Capture on h2 and replay from h1 (terminal A, at `mininet>`)

Telemetry is appended on **egress port 2** (host h2). Start capture, then replay slowly on h1.

### Live sniff (recommended)

Parses telemetry in Python on the wire — no intermediate pcap:

```text
mininet> h2 sh -c 'python3 /p4/control_plane/capture_inband.py --interface eth0 -n 10000 -o /p4/data/capture.jsonl &'
mininet> h1 sh -c 'tcpreplay --multiplier=0.001 -i eth0 /p4/data/mawi_10000.pcap'
```

Or use the helper script (same default):

```text
mininet> h2 sh /p4/scripts/capture_on_h2.sh /p4/data/capture.jsonl 10000 eth0 &
mininet> h1 sh -c 'tcpreplay --multiplier=0.001 -i eth0 /p4/data/mawi_10000.pcap'
```

Automated (third terminal while `make run-thrift` is up):

```bash
REPLAY_MULTIPLIER=0.001 make test-mawi
# -> data/capture.jsonl
```

### PCAP fallback (tcpdump)

```text
mininet> h2 sh -c 'tcpdump -i eth0 -s 0 -w /p4/data/capture.pcap -c 10000 &'
mininet> h1 sh -c 'tcpreplay --multiplier=0.001 -i eth0 /p4/data/mawi_10000.pcap'
```

Automated (h2 tcpdump):

```bash
CAPTURE_MODE=pcap CAPTURE_SOURCE=h2 REPLAY_MULTIPLIER=0.001 make test-mawi
```

### BMv2 switch pcap (port 2)

Mininet starts BMv2 with `--pcap pcaps/`. Traffic toward **h2** is recorded in `pcaps/s1-eth2.pcap` automatically — no tcpdump on h2.

```bash
# Shorthand
CAPTURE_MODE=switch REPLAY_MULTIPLIER=0.001 make test-mawi

# Equivalent
CAPTURE_MODE=pcap CAPTURE_SOURCE=switch REPLAY_MULTIPLIER=0.001 make test-mawi
```

Manual parse after replay:

```bash
python3 control_plane/pipeline_capture_jsonl.py --pcap pcaps/s1-eth2.pcap -n 10000
```

The switch pcap grows for the whole Mininet session; use `-n 10000` (or reset with a fresh `make run-thrift`) to limit analysis to the replay batch.

### UDP INT export

The switch clones each observed packet into a small UDP report (port **4790**) to collector **10.0.0.2** (h2). Original traffic is forwarded without the in-band trailer.

Configure export mode, then capture INT reports on h2:

```bash
# Thrift (make run-thrift):
python3 control_plane/set_export_mode_thrift.py --mode udp

# P4Runtime (make run-grpc):
python3 control_plane/set_export_mode_grpc.py --mode udp
```

Manual Mininet:

```text
mininet> h2 sh -c 'python3 /p4/control_plane/capture_udp_int.py --interface eth0 -n 10000 -o /p4/data/capture.jsonl &'
mininet> h1 sh -c 'tcpreplay --multiplier=0.001 -i eth0 /p4/data/mawi_10000.pcap'
```

Automated:

```bash
CAPTURE_MODE=udp CAPTURE_USE_GRPC=1 REPLAY_MULTIPLIER=0.001 make test-mawi
```

Wait until tcpreplay finishes and capture stops.

**Notes:**

- Original MAWI MAC/IP addresses are fine — the P4 program uses a port 1 ↔ 2 “dumb wire” and parses L3/L4 from whatever arrives on h1.
- MAWI packets are truncated (~96 B cap); TCP/UDP/ICMP headers are usually still present.
- If BMv2 drops or overloads, lower `--multiplier` further (e.g. `0.0001`).

## 6. Parse capture and plot (terminal B)

```bash
cd /p4
# After live sniff (default test-mawi path):
python3 control_plane/pipeline_capture_jsonl.py --capture-jsonl data/capture.jsonl

# After tcpdump pcap:
python3 control_plane/capture_inband.py --pcap data/capture.pcap
python3 control_plane/plot_capture_jsonl.py
# plots -> task2/results/n_<N>/plots/
```

Precomputed **`task2/results/n_10000/`** plots and fits are committed for [`../../notebooks/task3_comparison.ipynb`](../../notebooks/task3_comparison.ipynb).

Optional register snapshot for Task III:

```bash
sudo python3 control_plane/read_registers_thrift.py --max-flows 16384 -o data/registers.json
```

One-shot (live JSONL or pcap):

```bash
python3 control_plane/pipeline_capture_jsonl.py --capture-jsonl data/capture.jsonl --dump-registers data/registers.json
# or: python3 control_plane/pipeline_capture_jsonl.py --pcap data/capture.pcap --dump-registers data/registers.json
```

## 7. Stop

```text
mininet> exit
```

```bash
make stop
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `No trace found` in prepare script | Put `201302011400.dump.gz` in repo root; rebuild container if `/repo` mount missing |
| `simple_switch_CLI not found` | Run inside `task2-p4-env` after `make run-thrift` |
| `No telemetry-tagged packets` in capture | For `live`/`pcap`: capture on **h2**; for `udp`: run `set_export_mode_grpc.py --mode udp` and sniff port 4790 |
| Switch pcap empty / missing | Start with `make run-thrift` (BMv2 `--pcap pcaps/` is on by default); replay at least one packet |
| UDP mode empty capture | Run `make build` after P4 changes; ensure clone session configured (`set_export_mode_grpc.py`) |
| Capture empty | Reset registers before replay; check `make build` succeeded |
| Compare with Task I | Same first 10,000 packets of `201302011400`; Task I uses JSONL/tshark, Task II uses replay + switch timestamps (µs) and on-wire frame lengths |
