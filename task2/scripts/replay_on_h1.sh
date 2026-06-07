#!/usr/bin/env bash
# Replay the prepared MAWI subset on h1 (call from Mininet: h1 sh /p4/scripts/replay_on_h1.sh)
set -euo pipefail

PCAP="${1:-/p4/data/replay.pcap}"
# Inside Mininet hosts the NIC is eth0 (not h1-eth0 — that name is only on the host).
IFACE="${2:-eth0}"
MULT="${3:-${REPLAY_MULTIPLIER:-0.001}}"

if [[ ! -f "$PCAP" ]]; then
  echo "Missing $PCAP — run scripts/prepare_trace.sh first" >&2
  exit 1
fi

echo "Replaying $PCAP on $IFACE at multiplier=$MULT"
exec tcpreplay --multiplier="$MULT" -i "$IFACE" "$PCAP"
