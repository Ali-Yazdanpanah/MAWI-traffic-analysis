#!/usr/bin/env bash
# Remove regenerable build outputs (safe to re-run make build / plot_analysis).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Cleaning Task II build/runtime artifacts..."
rm -rf "$ROOT/task2/build" "$ROOT/task2/pcaps" "$ROOT/task2/logs" "$ROOT/task2/build-test"

echo "Removing Python caches..."
find "$ROOT/task1" "$ROOT/task2" "$ROOT/notebooks" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

echo "Done. Regenerate with:"
echo "  cd task2 && make build"
echo "  py -3.10 control_plane/plot_capture_jsonl.py data/capture.jsonl -n 10000"
