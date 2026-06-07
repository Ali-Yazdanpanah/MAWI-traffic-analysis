# Programmable Data Planes — Homework (Tasks I–III)

MAWI trace analysis in software (Task I), in-network telemetry on BMv2 (Task II), and comparison write-up (Task III).

**Homework deliverable:** [`notebooks/task3_comparison.ipynb`](notebooks/task3_comparison.ipynb) (plots, statistical fits, Task I vs Task II discussion). Source code and run instructions are in `task1/` and `task2/`.

## Trace alignment (Task I vs Task II)

Both tasks use the MAWI sample **`201302011400`** (96-byte snaplen, anonymized IPs). For the comparison at **N = 10,000**:

| Task | Input | Subset rule |
|------|--------|-------------|
| **Task I** | `201302011400.jsonl` (tshark export from the same capture) | First **10,000** records (`plot_analysis … -n 10000`) |
| **Task II** | `task2/data/mawi_10000.pcap` (`make trace-prepare`) | First **10,000** frames (`tcpdump -c 10000` on decompressed PCAP) |

That is the **same packet sequence** from the archive; measurements differ (offline dissection vs replayed frames, telemetry trailer, switch timestamps, hash-based flow IDs). See the notebook for details.

**Note:** `201302011400.*` trace files are gitignored. Download the [MAWI dump](http://mawi.wide.ad.jp/mawi/samplepoint-F/2013/201302011400.dump.gz) to the repo root, then export JSONL for Task I or run `make trace-prepare` in Task II.

## Layout

```
├── requirements.txt          # Shared Python deps (Task I + II analysis + scapy/gRPC)
├── scripts/
│   ├── setup_venv.sh         # Create root .venv
│   └── clean_artifacts.sh    # Remove build/logs/__pycache__
├── task1/                    # Software MAWI analysis
├── task2/                    # P4 / BMv2 / Mininet pipeline
├── notebooks/
│   └── task3_comparison.ipynb
├── 201302011400.jsonl        # Task I input (from MAWI dump)
└── 201302011400.dump.gz      # Task II replay input (place at repo root)
```

## Quick start

### Task I (host)

```bash
./scripts/setup_venv.sh
source .venv/bin/activate   # or: .venv\Scripts\activate on Windows
cd task1
python -m src.analysis.plot_analysis ../201302011400.jsonl -n 10000
```

Outputs: `task1/results/n_<N>/` (plots + `statistical-fits/`).

### Task II (Docker)

```bash
cd task2
docker compose build
docker compose up -d
docker exec -it task2-p4-env bash
cd /p4
make trace-prepare && make build && make run-grpc
```

See **[task2/README.md](task2/README.md)** for telemetry egress methods (in-band, UDP INT, register readout), P4, and full workflow.

### Task III

Report and side-by-side comparison: **[notebooks/task3_comparison.ipynb](notebooks/task3_comparison.ipynb)** (uses committed outputs under `task1/results/n_10000/` and `task2/results/n_10000/`).

## Analysis outputs

| Path | Regenerate |
|------|------------|
| `task1/results/n_10000/` | Task I `plot_analysis` (committed for submission) |
| `task2/results/n_10000/` | Task II `pipeline_capture_jsonl` (committed for submission) |
| `task2/build/`, `pcaps/`, `logs/` | `make build`, `make run-thrift` |
| `task2/data/capture.jsonl` | `make test-mawi` |

Clean build outputs: `./scripts/clean_artifacts.sh`

## Documentation

| Doc | Content |
|-----|---------|
| [task1/README.md](task1/README.md) | Task I extraction + analysis |
| [task2/README.md](task2/README.md) | Task II architecture + reference |
| [task2/docs/RUN_WITH_MAWI.md](task2/docs/RUN_WITH_MAWI.md) | Step-by-step MAWI replay |
