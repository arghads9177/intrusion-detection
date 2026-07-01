#!/usr/bin/env bash
#
# Start the full PIDS POC stack with one command:
#   1. RTSP simulation (MediaMTX + ffmpeg loops)
#   2. Analytics workers (one per enabled camera in config/cameras.yaml, headless)
#   3. FastAPI backend (uvicorn)
#   4. Angular dashboard (ng serve)
#
# Logs go to scripts/logs/, PIDs go to scripts/.pids/ (used by stop_all.sh).
#
# Usage: ./scripts/start_all.sh [--generate]
#   --generate   Re-create synthetic sample videos before streaming

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$SCRIPT_DIR/.pids"
LOG_DIR="$SCRIPT_DIR/logs"
VENV_PY="$PROJECT_DIR/.venv/bin/python"

CAMERAS=("cam1" "cam2")

# mediamtx isn't installed system-wide; fall back to the static binary from the
# sibling fire-smoke-detection project if nothing is found on PATH.
FALLBACK_MEDIAMTX="/home/argha-ds/datascience/computer vision/fire & smoke detection/fire-smoke-detection/simulator/bin/mediamtx"
if ! command -v "${MEDIAMTX_BIN:-mediamtx}" &>/dev/null && [ -x "$FALLBACK_MEDIAMTX" ]; then
    export MEDIAMTX_BIN="$FALLBACK_MEDIAMTX"
fi

mkdir -p "$PID_DIR" "$LOG_DIR"

start_bg() {
    local name="$1"
    shift
    echo "Starting $name..."
    ( cd "$PROJECT_DIR" && "$@" ) &>"$LOG_DIR/${name}.log" &
    echo "$!" > "$PID_DIR/${name}.pid"
    sleep 1
    if ! kill -0 "$(cat "$PID_DIR/${name}.pid")" 2>/dev/null; then
        echo "  ERROR: $name failed to start. Check $LOG_DIR/${name}.log"
        return 1
    fi
    echo "  $name started (PID $(cat "$PID_DIR/${name}.pid"))."
}

# ---------------------------------------------------------------------------
# 1. RTSP simulation
# ---------------------------------------------------------------------------
echo "=== 1/4  RTSP simulation ==="
"$PROJECT_DIR/sim/start_streams.sh" ${1:-} &>"$LOG_DIR/sim.log" &
disown
sleep 3
echo "  RTSP streams launching in background (log: $LOG_DIR/sim.log)."

# ---------------------------------------------------------------------------
# 2. Analytics workers (AI inference), one per camera
# ---------------------------------------------------------------------------
echo ""
echo "=== 2/4  Analytics workers ==="
for cam in "${CAMERAS[@]}"; do
    start_bg "worker_${cam}" "$VENV_PY" -m analytics.worker --camera "$cam" --headless
done

# ---------------------------------------------------------------------------
# 3. Backend (FastAPI)
# ---------------------------------------------------------------------------
echo ""
echo "=== 3/4  Backend ==="
start_bg "backend" "$VENV_PY" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# ---------------------------------------------------------------------------
# 4. Dashboard (Angular)
# ---------------------------------------------------------------------------
echo ""
echo "=== 4/4  Dashboard ==="
start_bg "dashboard" bash -c "cd '$PROJECT_DIR/dashboard' && npm start"

echo ""
echo "=== PIDS POC stack is up ==="
echo "  Backend:   http://localhost:8000/docs"
echo "  Dashboard: http://localhost:4200"
echo "  Logs:      $LOG_DIR/"
echo "  Stop with: ./scripts/stop_all.sh"
