#!/usr/bin/env bash
# Capture telemetry on h2 (call from Mininet: h2 sh /p4/scripts/capture_on_h2.sh)
#
# CAPTURE_MODE:
#   live  - Scapy in-band telemetry sniff -> JSONL (default)
#   pcap  - tcpdump -> pcap
#   udp   - Scapy UDP INT reports -> JSONL
set -euo pipefail

P4_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-/p4/data/capture.jsonl}"
COUNT="${2:-${PACKET_LIMIT:-10000}}"
IFACE="${3:-eth0}"
CAPTURE_MODE="${CAPTURE_MODE:-live}"
CAPTURE_TIMEOUT="${CAPTURE_TIMEOUT:-300}"
INT_UDP_PORT="${INT_UDP_PORT:-4790}"

mkdir -p "$(dirname "$OUT")"

if [[ "$CAPTURE_MODE" == "pcap" ]]; then
    echo "Capturing up to $COUNT packets on $IFACE -> $OUT (tcpdump)"
    exec tcpdump -i "$IFACE" -s 0 -w "$OUT" -c "$COUNT"
fi

if [[ "$CAPTURE_MODE" == "udp" ]]; then
    echo "UDP INT capture: up to $COUNT reports on $IFACE port $INT_UDP_PORT -> $OUT"
    exec python3 "$P4_ROOT/control_plane/capture_udp_int.py" \
        --interface "$IFACE" \
        -n "$COUNT" \
        --timeout "$CAPTURE_TIMEOUT" \
        --udp-port "$INT_UDP_PORT" \
        -o "$OUT"
fi

echo "Live in-band sniff: up to $COUNT frames on $IFACE -> $OUT"
exec python3 "$P4_ROOT/control_plane/capture_inband.py" \
    --interface "$IFACE" \
    -n "$COUNT" \
    --timeout "$CAPTURE_TIMEOUT" \
    -o "$OUT"
