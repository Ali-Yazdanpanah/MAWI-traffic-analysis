#!/usr/bin/env bash
# Decompress MAWI dump.gz and build a replayable PCAP subset for Task II.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P4_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REPO="${REPO_ROOT:-/repo}"
OUT="${OUT_DIR:-$P4_ROOT/data}"
LIMIT="${PACKET_LIMIT:-10000}"
MULTIPLIER="${REPLAY_MULTIPLIER:-0.001}"

# Search order: explicit path, repo root mount, task2/data, p4/data
if [[ -n "${TRACE_GZ:-}" ]]; then
  GZ="$TRACE_GZ"
elif [[ -f "$REPO/201302011400.dump.gz" ]]; then
  GZ="$REPO/201302011400.dump.gz"
elif [[ -f "$P4_ROOT/data/201302011400.dump.gz" ]]; then
  GZ="$P4_ROOT/data/201302011400.dump.gz"
else
  GZ=""
fi

RAW="$OUT/201302011400.pcap"
SUBSET="$OUT/mawi_${LIMIT}.pcap"
LINK="$OUT/replay.pcap"

mkdir -p "$OUT"

if [[ -f "$RAW" ]]; then
  echo "Using existing $RAW"
elif [[ -n "$GZ" && -f "$GZ" ]]; then
  echo "Decompressing $GZ -> $RAW (this may take a minute)"
  gunzip -c "$GZ" > "$RAW"
elif [[ -f "$REPO/201302011400.pcap" ]]; then
  cp "$REPO/201302011400.pcap" "$RAW"
elif [[ -f "$P4_ROOT/data/201302011400.pcap" ]]; then
  cp "$P4_ROOT/data/201302011400.pcap" "$RAW"
else
  echo "No MAWI trace found." >&2
  echo "Place 201302011400.dump.gz at repo root or task2/data/, or set TRACE_GZ=" >&2
  exit 1
fi

echo "Writing first ${LIMIT} packets -> $SUBSET"
tcpdump -r "$RAW" -w "$SUBSET" -c "$LIMIT" 2>/dev/null
ln -sf "$(basename "$SUBSET")" "$LINK"
echo "Ready for replay:"
echo "  subset: $SUBSET"
echo "  link:   $LINK"
echo ""
echo "Inside mininet (after 'make run'):"
echo "  mininet> h2 sh -c 'nohup /p4/scripts/capture_on_h2.sh /p4/data/capture.pcap ${LIMIT} >/tmp/capture.log 2>&1 & sleep 2'"
echo "  mininet> h1 sh -c '/p4/scripts/replay_on_h1.sh /p4/data/replay.pcap'"
echo ""
echo "Source trace: ${GZ:-$RAW} (from 201302011400.dump.gz via make trace-prepare)"
echo "Ignore pcaps/ — those are BMv2 switch debug dumps, not the MAWI replay file."
