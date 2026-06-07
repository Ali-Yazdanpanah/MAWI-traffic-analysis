# Programmable Data Planes — Homework (Tasks I–III)

MAWI trace analysis in software (Task I), in-network telemetry on BMv2 (Task II), and comparison write-up (Task III).

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

Fill in **[notebooks/task3_comparison.ipynb](notebooks/task3_comparison.ipynb)** using Task I/II results.

## Regenerable artifacts (gitignored)

| Path | Regenerate |
|------|------------|
| `task1/results/` | Task I `plot_analysis` |
| `task2/results/` | Task II `plot_analysis` / `run_pipeline` |
| `task2/build/`, `pcaps/`, `logs/` | `make build`, `make run` |
| `task2/data/capture.jsonl` | `make test-mawi` |

Clean build outputs: `./scripts/clean_artifacts.sh`

## Documentation

| Doc | Content |
|-----|---------|
| [task1/README.md](task1/README.md) | Task I extraction + analysis |
| [task2/README.md](task2/README.md) | Task II architecture + reference |
| [task2/docs/RUN_WITH_MAWI.md](task2/docs/RUN_WITH_MAWI.md) | Step-by-step MAWI replay |
