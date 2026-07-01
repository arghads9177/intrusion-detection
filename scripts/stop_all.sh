#!/usr/bin/env bash
#
# Stop the full PIDS POC stack started by start_all.sh:
#   analytics workers, backend, dashboard, and the RTSP simulation.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$SCRIPT_DIR/.pids"

stop_process() {
    local name="$1"
    local pidfile="$PID_DIR/${name}.pid"

    if [ -f "$pidfile" ]; then
        local pid
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            # Kill the whole process group so wrapped children (npm -> ng, etc.) die too.
            pkill -P "$pid" 2>/dev/null || true
            kill "$pid" 2>/dev/null || true
            echo "Stopped $name (PID $pid)."
        else
            echo "$name (PID $pid) not running."
        fi
        rm -f "$pidfile"
    else
        echo "$name: no PID file, skipping."
    fi
}

echo "=== Stopping dashboard ==="
stop_process "dashboard"
pkill -f "ng serve" 2>/dev/null && echo "Killed remaining 'ng serve' processes." || true

echo ""
echo "=== Stopping backend ==="
stop_process "backend"

echo ""
echo "=== Stopping analytics workers ==="
stop_process "worker_cam1"
stop_process "worker_cam2"
pkill -f "analytics.worker" 2>/dev/null && echo "Killed remaining analytics.worker processes." || true

echo ""
echo "=== Stopping RTSP simulation ==="
"$PROJECT_DIR/sim/stop_streams.sh" || true

rmdir "$PID_DIR" 2>/dev/null || true

echo ""
echo "All PIDS POC services stopped."
