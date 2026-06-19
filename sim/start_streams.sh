#!/usr/bin/env bash
#
# Start CCTV simulation: MediaMTX RTSP server + ffmpeg loops.
# Produces rtsp://localhost:8554/cam1 and rtsp://localhost:8554/cam2.
#
# Usage: ./sim/start_streams.sh [--generate]
#   --generate   Re-create synthetic sample videos before streaming

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SAMPLES_DIR="$SCRIPT_DIR/samples"
PID_DIR="$SCRIPT_DIR/.pids"

RTSP_PORT="${RTSP_PORT:-8554}"
MEDIAMTX_BIN="${MEDIAMTX_BIN:-mediamtx}"

CAM1_FILE="${CAM1_FILE:-$SAMPLES_DIR/person_intrusion.mp4}"
CAM2_FILE="${CAM2_FILE:-$SAMPLES_DIR/animal_motion.mp4}"

cleanup() {
    echo ""
    echo "Shutting down streams..."
    "$SCRIPT_DIR/stop_streams.sh" 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
for cmd in ffmpeg "$MEDIAMTX_BIN"; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: '$cmd' not found in PATH."
        echo "Install it first (see README.md Prerequisites)."
        exit 1
    fi
done

# Generate sample videos if requested or if none exist
if [[ "${1:-}" == "--generate" ]] || [ ! -f "$CAM1_FILE" ] || [ ! -f "$CAM2_FILE" ]; then
    echo "Generating sample videos..."
    python3 "$SCRIPT_DIR/generate_samples.py" --force
fi

if [ ! -f "$CAM1_FILE" ]; then
    echo "ERROR: cam1 video not found at $CAM1_FILE"
    exit 1
fi
if [ ! -f "$CAM2_FILE" ]; then
    echo "ERROR: cam2 video not found at $CAM2_FILE"
    exit 1
fi

mkdir -p "$PID_DIR"

# ---------------------------------------------------------------------------
# Start MediaMTX (if not already running)
# ---------------------------------------------------------------------------
if pgrep -x mediamtx &>/dev/null; then
    echo "MediaMTX already running (PID $(pgrep -x mediamtx))."
else
    echo "Starting MediaMTX on port $RTSP_PORT..."
    $MEDIAMTX_BIN &>"$SCRIPT_DIR/mediamtx.log" &
    MTX_PID=$!
    echo "$MTX_PID" > "$PID_DIR/mediamtx.pid"
    sleep 2

    if ! kill -0 "$MTX_PID" 2>/dev/null; then
        echo "ERROR: MediaMTX failed to start. Check sim/mediamtx.log"
        exit 1
    fi
    echo "  MediaMTX started (PID $MTX_PID)."
fi

# ---------------------------------------------------------------------------
# Start ffmpeg loops
# ---------------------------------------------------------------------------
start_stream() {
    local cam_name="$1"
    local video_file="$2"

    echo "Starting stream: rtsp://localhost:$RTSP_PORT/$cam_name -> $(basename "$video_file")"

    ffmpeg \
        -re \
        -stream_loop -1 \
        -i "$video_file" \
        -c copy \
        -f rtsp \
        "rtsp://localhost:$RTSP_PORT/$cam_name" \
        &>"$SCRIPT_DIR/ffmpeg_${cam_name}.log" &

    local pid=$!
    echo "$pid" > "$PID_DIR/ffmpeg_${cam_name}.pid"

    sleep 1
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "  WARN: ffmpeg for $cam_name exited immediately."
        echo "  Retrying with re-encoding (-c:v libx264)..."

        ffmpeg \
            -re \
            -stream_loop -1 \
            -i "$video_file" \
            -c:v libx264 -preset ultrafast -tune zerolatency \
            -c:a aac \
            -f rtsp \
            "rtsp://localhost:$RTSP_PORT/$cam_name" \
            &>"$SCRIPT_DIR/ffmpeg_${cam_name}.log" &

        pid=$!
        echo "$pid" > "$PID_DIR/ffmpeg_${cam_name}.pid"
        sleep 1

        if ! kill -0 "$pid" 2>/dev/null; then
            echo "  ERROR: ffmpeg for $cam_name failed even with re-encoding."
            echo "  Check sim/ffmpeg_${cam_name}.log for details."
            return 1
        fi
    fi

    echo "  $cam_name streaming (PID $pid)."
}

start_stream "cam1" "$CAM1_FILE"
start_stream "cam2" "$CAM2_FILE"

echo ""
echo "=== CCTV Simulation Running ==="
echo "  cam1: rtsp://localhost:$RTSP_PORT/cam1  ($(basename "$CAM1_FILE"))"
echo "  cam2: rtsp://localhost:$RTSP_PORT/cam2  ($(basename "$CAM2_FILE"))"
echo ""
echo "Verify with:  ffplay rtsp://localhost:$RTSP_PORT/cam1"
echo "Stop with:    ./sim/stop_streams.sh"
echo ""
echo "Press Ctrl+C to stop all streams."

wait
