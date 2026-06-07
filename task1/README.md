# Task I — Software MAWI Analysis

Offline analysis of the MAWI trace: packet/flow/timeseries features, distributions, and statistical fits.

## Input data

| File | Source |
|------|--------|
| `../201302011400.dump.gz` | [MAWI sample](http://mawi.wide.ad.jp/mawi/samplepoint-F/2013/201302011400.dump.gz) |
| `../201302011400.jsonl` | Flattened export for analysis (see extraction below) |

## Setup

From repo root:

```bash
./scripts/setup_venv.sh
source .venv/bin/activate
```

## Extract PCAP → JSONL (once)

```bash
cd task1
python -m src.extraction.extract_pcap_to_json \
  --pcap ../201302011400.pcap \
  --output ../201302011400.jsonl
```

## Run analysis

```bash
python -m src.analysis.plot_analysis ../201302011400.jsonl -n 10000
```

Options:

- `-n 10000` — packet limit
- `-o path/to/results` — custom results root
- `--no-fits` — plots only, skip scipy fits

## Output layout

```
task1/results/n_<N>/
├── plots/
│   ├── packet/{features,distribution}/
│   ├── flow/{features,distribution}/
│   ├── timeseries/{features,distribution}/
│   └── statistical-fits/
└── statistical-fits/
    ├── best_fits_summary.csv
    └── by_segment/ ...
```

## Code layout

```
task1/src/
├── extraction/extract_pcap_to_json.py   # tshark → JSONL
└── analysis/
    ├── bootstrap.py                     # Load JSONL → DataFrames
    ├── distribution_fitting.py          # scipy MLE + GoF
    ├── statistical_fits.py              # Fit orchestration
    ├── plot_analysis.py                 # Main entry point
    ├── results_paths.py                 # Output path helpers
    ├── packet/                          # Per-packet plots
    ├── flow/                            # Per-flow plots
    └── timeseries/                      # Time-series plots
```

Task II reuses this analysis stack via `task2/control_plane/loaders.py`.
