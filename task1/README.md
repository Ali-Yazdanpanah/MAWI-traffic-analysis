# Task I — Software MAWI Analysis

Offline analysis of the MAWI trace: packet/flow/timeseries features, distributions, and statistical fits.

Task III compares these results against Task II at **N = 10,000** using [`../notebooks/task3_comparison.ipynb`](../notebooks/task3_comparison.ipynb).

## Input data

| File | Source |
|------|--------|
| `../201302011400.dump.gz` | [MAWI sample](http://mawi.wide.ad.jp/mawi/samplepoint-F/2013/201302011400.dump.gz) |
| `../201302011400.jsonl` | Flattened export for analysis (see extraction below; gitignored until generated) |

**Alignment with Task II:** Task II replays `task2/data/mawi_10000.pcap`, the first 10,000 frames cut from the same decompressed capture. Task I should analyze the matching head of the trace: either export JSONL with `--limit-packets 10000`, or run `plot_analysis` with `-n 10000` on a longer JSONL built in file order from the same PCAP.

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
  --output ../201302011400.jsonl \
  --limit-packets 10000
```

For a longer export, omit `--limit-packets` and pass `-n 10000` to `plot_analysis` so analysis still uses the first 10,000 records in file order.

## Run analysis

```bash
python -m src.analysis.plot_analysis ../201302011400.jsonl -n 10000
```

Outputs: `task1/results/n_<N>/` (plots + `statistical-fits/`). Precomputed **`n_10000`** results are committed for submission.

Options:

- `-n 10000` — packet limit (homework comparison size)
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
    ├── best_fits_summary.csv      # aggregate (segment=all) + all breakdown rows
    ├── iat_pdf_fit.png            # overall plots per metric
    └── by_segment/<breakdown>/
        ├── best_fits_summary.csv  # overall (__all) + per-group rows
        └── iat__all_pdf_fit.png   # aggregate copied alongside iat__tcp, …
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

Task II reuses this analysis stack via `task2/control_plane/analysis_loader_bridge.py`.
