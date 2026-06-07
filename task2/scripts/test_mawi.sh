#!/usr/bin/env bash
# Automate MAWI replay: capture on h2, inject on h1 (Mininet must already be running).
#
# CAPTURE_MODE — switch export + collector type:
#   live   - in-band telemetry, Scapy sniff on h2 (default)
#   pcap   - in-band telemetry, pcap file
#   udp    - UDP INT reports, Scapy on h2 (requires CAPTURE_SOURCE=h2)
#   switch - shorthand for in-band telemetry from BMv2 pcaps/s1-eth2.pcap
#
# CAPTURE_SOURCE — where in-band/pcap data comes from (pcap/live modes):
#   h2     - tcpdump or Scapy on host h2 (default)
#   switch - BMv2 auto-dump on s1 port 2 (pcaps/s1-eth2.pcap)
#
# Examples:
#   REPLAY_MULTIPLIER=0.001 make test-mawi
#   CAPTURE_MODE=pcap CAPTURE_SOURCE=h2 make test-mawi
#   CAPTURE_MODE=pcap CAPTURE_SOURCE=switch make test-mawi
#   CAPTURE_MODE=switch make test-mawi
#   CAPTURE_MODE=udp CAPTURE_USE_GRPC=1 make test-mawi
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
P4_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

COUNT="${PACKET_LIMIT:-10000}"
MULT="${REPLAY_MULTIPLIER:-0.01}"
PCAP="${REPLAY_PCAP:-$P4_ROOT/data/mawi_${COUNT}.pcap}"
CAPTURE="${CAPTURE_PCAP:-$P4_ROOT/data/capture.pcap}"
CAPTURE_JSONL="${CAPTURE_JSONL:-$P4_ROOT/data/capture.jsonl}"
CAPTURE_MODE="${CAPTURE_MODE:-live}"
CAPTURE_SOURCE="${CAPTURE_SOURCE:-h2}"
CAPTURE_TIMEOUT="${CAPTURE_TIMEOUT:-300}"
CAPTURE_USE_GRPC="${CAPTURE_USE_GRPC:-0}"
INT_UDP_PORT="${INT_UDP_PORT:-4790}"
SWITCH_PCAP="${SWITCH_PCAP:-$P4_ROOT/pcaps/s1-eth2.pcap}"
H_IFACE="${MININET_HOST_IFACE:-eth0}"

MNEXEC="${MNEXEC:-mnexec}"

# Resolved after validate_capture_settings().
EFFECTIVE_MODE=""
EFFECTIVE_SOURCE=""
EFFECTIVE_PCAP=""

host_pid() {
    local host="$1"
    local pid
    pid="$(pgrep -f "mininet:${host}" | head -1 || true)"
    if [[ -z "$pid" ]]; then
        return 1
    fi
    echo "$pid"
}

require_mininet() {
    if ! command -v "$MNEXEC" >/dev/null 2>&1; then
        echo "Missing $MNEXEC -- install/run Mininet (make run) first." >&2
        exit 1
    fi
    if ! command -v pgrep >/dev/null 2>&1; then
        echo "Missing pgrep (procps) -- required to find Mininet host PIDs." >&2
        exit 1
    fi
    if ! host_pid h1 >/dev/null; then
        echo "Mininet hosts not available. Start the topology in another terminal:" >&2
        echo "  cd $P4_ROOT && make run   # or make run-grpc" >&2
        exit 1
    fi
}

validate_capture_settings() {
    case "$CAPTURE_MODE" in
        live|pcap|udp|switch) ;;
        *)
            echo "Invalid CAPTURE_MODE=$CAPTURE_MODE (use live, pcap, udp, or switch)" >&2
            exit 1
            ;;
    esac

    case "$CAPTURE_SOURCE" in
        h2|switch) ;;
        *)
            echo "Invalid CAPTURE_SOURCE=$CAPTURE_SOURCE (use h2 or switch)" >&2
            exit 1
            ;;
    esac

    if [[ "$CAPTURE_MODE" == "switch" ]]; then
        EFFECTIVE_MODE="pcap"
        EFFECTIVE_SOURCE="switch"
    else
        EFFECTIVE_MODE="$CAPTURE_MODE"
        EFFECTIVE_SOURCE="$CAPTURE_SOURCE"
    fi

    if [[ "$EFFECTIVE_MODE" == "udp" && "$EFFECTIVE_SOURCE" == "switch" ]]; then
        echo "CAPTURE_MODE=udp requires CAPTURE_SOURCE=h2 (INT reports are delivered to h2)." >&2
        exit 1
    fi

    if [[ "$EFFECTIVE_SOURCE" == "switch" ]]; then
        EFFECTIVE_PCAP="$SWITCH_PCAP"
    else
        EFFECTIVE_PCAP="$CAPTURE"
    fi
}

require_pcap() {
    if [[ ! -f "$PCAP" ]]; then
        echo "Missing $PCAP" >&2
        echo "Run: PACKET_LIMIT=$COUNT make trace-prepare" >&2
        exit 1
    fi
}

run_host() {
    local host="$1"
    local pid
    shift
    pid="$(host_pid "$host")" || {
        echo "Mininet host '$host' not running." >&2
        exit 1
    }
    sudo "$MNEXEC" -a "$pid" "$@"
}

configure_switch_export() {
    local grpc_args=()
    local export_capture_mode="$CAPTURE_MODE"
    if [[ "$CAPTURE_MODE" == "switch" ]]; then
        export_capture_mode="pcap"
    fi
    if [[ "$CAPTURE_USE_GRPC" == "1" ]]; then
        grpc_args=(--use-grpc)
    fi
    echo "Configuring switch telemetry export for CAPTURE_MODE=$CAPTURE_MODE..."
    if ! python3 "$P4_ROOT/control_plane/set_export_mode.py" \
        --capture-mode "$export_capture_mode" "${grpc_args[@]}"; then
        echo "Warning: could not set export mode (run make build after P4 changes?)" >&2
    fi
}

stop_h2_tcpdump() {
    local job_pid="${1:-}"
    if [[ -n "$job_pid" ]] && kill -0 "$job_pid" 2>/dev/null; then
        kill -INT "$job_pid" 2>/dev/null || true
        sleep 0.5
        kill -TERM "$job_pid" 2>/dev/null || true
        sleep 0.5
        kill -KILL "$job_pid" 2>/dev/null || true
    fi
    run_host h2 pkill -INT -x tcpdump 2>/dev/null || true
    run_host h2 pkill -TERM -x tcpdump 2>/dev/null || true
}

stop_h2_sniff() {
    local job_pid="${1:-}"
    if [[ -n "$job_pid" ]] && kill -0 "$job_pid" 2>/dev/null; then
        kill -INT "$job_pid" 2>/dev/null || true
        sleep 0.5
        kill -TERM "$job_pid" 2>/dev/null || true
        sleep 0.5
        kill -KILL "$job_pid" 2>/dev/null || true
    fi
    if command -v timeout >/dev/null 2>&1; then
        timeout 5 wait "$job_pid" 2>/dev/null || true
    fi
}

count_pcap_packets() {
    local path="$1"
    if python3 -c "from scapy.utils import PcapReader" >/dev/null 2>&1; then
        python3 - "$path" <<'PY'
import sys
from scapy.all import conf
from scapy.utils import PcapReader

conf.verb = 0
path = sys.argv[1]
print(sum(1 for _ in PcapReader(path)))
PY
        return
    fi
    tcpdump -r "$path" 2>/dev/null | wc -l | tr -d ' '
}

count_jsonl_lines() {
    local path="$1"
    if [[ ! -f "$path" ]]; then
        echo 0
        return
    fi
    wc -l < "$path" | tr -d ' '
}

print_collector_summary() {
    echo "  capture mode:  $CAPTURE_MODE"
    echo "  capture source: $EFFECTIVE_SOURCE"
    case "$EFFECTIVE_MODE" in
        live)
            if [[ "$EFFECTIVE_SOURCE" == "switch" ]]; then
                echo "  collector:     BMv2 switch pcap -> $EFFECTIVE_PCAP"
            else
                echo "  collector:     live in-band sniff on h2 -> $CAPTURE_JSONL"
            fi
            ;;
        pcap)
            if [[ "$EFFECTIVE_SOURCE" == "switch" ]]; then
                echo "  collector:     BMv2 switch pcap -> $EFFECTIVE_PCAP"
            else
                echo "  collector:     h2 tcpdump -> $EFFECTIVE_PCAP"
            fi
            ;;
        udp)
            echo "  collector:     UDP INT on h2 port $INT_UDP_PORT -> $CAPTURE_JSONL"
            ;;
    esac
}

main() {
    require_mininet
    validate_capture_settings
    require_pcap

    mkdir -p "$(dirname "$CAPTURE")" "$(dirname "$CAPTURE_JSONL")"
    rm -f "$CAPTURE" "$CAPTURE_JSONL"

    echo "=== MAWI replay test ==="
    echo "  replay:        $PCAP"
    print_collector_summary
    if [[ "$EFFECTIVE_SOURCE" == "switch" ]]; then
        echo "  note:          $EFFECTIVE_PCAP accumulates for the whole Mininet run; use -n when plotting"
    fi
    if [[ "$EFFECTIVE_SOURCE" == "h2" && "$EFFECTIVE_MODE" != "pcap" ]]; then
        echo "  sniff timeout: ${CAPTURE_TIMEOUT}s"
    fi
    echo "  rate:          multiplier=$MULT on h1 ($H_IFACE)"
    echo ""

    configure_switch_export

    capture_pid=""
    if [[ "$EFFECTIVE_SOURCE" == "h2" ]]; then
        if [[ "$EFFECTIVE_MODE" == "pcap" ]]; then
            run_host h2 pkill -TERM -x tcpdump 2>/dev/null || true
            echo "Starting tcpdump on h2 (background)..."
            run_host h2 tcpdump -i "$H_IFACE" -s 0 -w "$CAPTURE" &
            capture_pid=$!
        elif [[ "$EFFECTIVE_MODE" == "live" || "$EFFECTIVE_MODE" == "udp" ]]; then
            echo "Starting collector on h2 (background)..."
            capture_args=(
                python3 "$P4_ROOT/control_plane/capture_packets.py"
                --interface "$H_IFACE"
                -n "$COUNT"
                --timeout "$CAPTURE_TIMEOUT"
                -o "$CAPTURE_JSONL"
            )
            if [[ "$EFFECTIVE_MODE" == "udp" ]]; then
                capture_args+=(--int-udp --udp-port "$INT_UDP_PORT")
            fi
            run_host h2 "${capture_args[@]}" &
            capture_pid=$!
        fi
        sleep 2
    else
        echo "Using BMv2 switch pcap (no collector on h2)..."
        if [[ ! -f "$EFFECTIVE_PCAP" ]]; then
            echo "Note: $EFFECTIVE_PCAP not found yet; BMv2 creates it after the first packet on port 2." >&2
        fi
    fi

    echo "Starting tcpreplay on h1 (foreground)..."
    run_host h1 tcpreplay --multiplier="$MULT" -i "$H_IFACE" "$PCAP"

    echo ""
    if [[ "$EFFECTIVE_SOURCE" == "switch" || "$EFFECTIVE_MODE" == "pcap" ]]; then
        if [[ -n "$capture_pid" ]]; then
            echo "Stopping tcpdump on h2 (replay finished)..."
            stop_h2_tcpdump "$capture_pid"
            if command -v timeout >/dev/null 2>&1; then
                timeout 2 wait "$capture_pid" 2>/dev/null || true
            fi
        else
            sleep 1
        fi
        if [[ ! -f "$EFFECTIVE_PCAP" ]]; then
            echo "Missing $EFFECTIVE_PCAP after replay." >&2
            echo "Ensure Mininet was started with BMv2 --pcap (default via make run)." >&2
            exit 1
        fi
        captured="$(count_pcap_packets "$EFFECTIVE_PCAP")"
        echo "Packets in $EFFECTIVE_PCAP: $captured"
        rel_pcap="${EFFECTIVE_PCAP#"$P4_ROOT/"}"
        echo "Done. Parse/plot:"
        echo "  python3 control_plane/run_pipeline.py --pcap $rel_pcap -n $COUNT"
    else
        echo "Stopping collector on h2 (replay finished)..."
        stop_h2_sniff "$capture_pid"
        captured="$(count_jsonl_lines "$CAPTURE_JSONL")"
        echo "Captured telemetry records in $CAPTURE_JSONL: $captured"
        echo "Done. Plot:"
        echo "  python3 control_plane/run_pipeline.py --capture-jsonl data/capture.jsonl -n $captured"
    fi

    if [[ "$captured" -lt "$COUNT" ]]; then
        echo "Note: target was $COUNT telemetry records but found $captured." >&2
        echo "      BMv2 may be dropping under load; try REPLAY_MULTIPLIER=0.001 make test-mawi" >&2
        if [[ "$EFFECTIVE_SOURCE" == "switch" ]]; then
            echo "      Switch pcaps include the whole session; pipeline -n selects the first N telemetry frames." >&2
        fi
    fi
}

main "$@"
