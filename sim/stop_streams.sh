#!/usr/bin/env bash
#
# Stop all CCTV simulation processes (ffmpeg streams + MediaMTX).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"

stop_process() {
    local name="$1"
    local pidfile="$PID_DIR/${name}.pid"

    if [ -f "$pidfile" ]; then
        local pid
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            echo "Stopped $name (PID $pid)."
        else
            echo "$name (PID $pid) not running."
        fi
        rm -f "$pidfile"
    fi
}

stop_process "ffmpeg_cam1"
stop_process "ffmpeg_cam2"
stop_process "mediamtx"

# Clean up any stray ffmpeg RTSP processes
pkill -f "ffmpeg.*rtsp://localhost" 2>/dev/null && echo "Killed remaining ffmpeg RTSP processes." || true

rmdir "$PID_DIR" 2>/dev/null || true

echo "All streams stopped."
