# SAIL-ISP PIDS — Intrusion Detection POC

Perimeter Intrusion Detection System proof-of-concept that demonstrates end-to-end video-analytics-based intrusion detection using simulated CCTV feeds.

A person crossing a defined perimeter zone is detected via YOLOv8, filtered against animals/environmental false alarms, evaluated against time-window and zone rules, and surfaced as an alert through a FastAPI backend, MongoDB, and an Angular 19 dashboard.

## What this POC demonstrates

| Capability | Description |
|------------|-------------|
| Human intrusion detection | Detect a person entering a defined perimeter zone |
| False-alarm filtering | Distinguish humans from animals, birds, and environmental motion — suppress non-threats |
| After-hours / zone rules | Time-window logic (e.g. alerts only outside working hours) and configurable detection zones |
| CCTV simulation | Re-stream recorded video over local RTSP so the pipeline ingests real `rtsp://` URLs |
| Alert generation | Event with snapshot, video clip, and metadata pushed to dashboard in real time |
| Full mini-stack | FastAPI backend + MongoDB + Angular 19 dashboard (live view, event log, stats) |

## Architecture

```
Sample videos --> [MediaMTX RTSP server] --> rtsp://localhost:8554/cam1, cam2
  (.mp4 looped        |
   via ffmpeg)        v
              +--------------------+
              | Analytics Worker   |
              | 1. RTSP ingest     |
              | 2. YOLOv8 detect   |
              | 3. Class filter    |
              | 4. Zone + rules    |
              | 5. Event + snapshot |
              +---------+----------+
                        | event
                        v
              +--------------------+       +-----------------+
              | FastAPI backend    | ----> | Angular 19 SPA  |
              | REST + WebSocket   |       | (dashboard)     |
              +---------+----------+       +-----------------+
                        |
                        v
              +--------------------+       +-----------------+
              | MongoDB            |       | media/          |
              | events, cameras,   |       | snapshots/      |
              | zones, rules       |       | clips/          |
              +--------------------+       +-----------------+
```

## Target environment

- **Machine:** Intel i7-7500U (2c/4t), 15 GB RAM, Intel HD 620 — no NVIDIA GPU
- **Inference:** CPU-only, `yolov8n` (nano), throttled to 3-5 FPS
- **Cameras:** 1-2 simulated via RTSP

## Tech stack

| Layer | Technology |
|-------|------------|
| CCTV simulation | MediaMTX + ffmpeg |
| Video ingest | OpenCV (`cv2.VideoCapture`) |
| Detection | Ultralytics YOLOv8 (`yolov8n`), CPU/PyTorch |
| Tracking | ByteTrack (Ultralytics built-in) |
| Zone logic | Shapely (point-in-polygon) |
| Backend | FastAPI + Uvicorn |
| Database | MongoDB (PyMongo + Motor) |
| Dashboard | Angular 19 + Angular Material + Chart.js |
| Media storage | Local filesystem (`media/`) |

## Prerequisites

Install the following before setup:

- **Python 3.10+**
- **Node.js 18+** and npm
- **MongoDB** (default `localhost:27017`)
- **MediaMTX** ([github.com/bluenviron/mediamtx](https://github.com/bluenviron/mediamtx))
- **ffmpeg**

## Setup

```bash
# Clone
git clone <repo-url> && cd pids-poc

# Python environment (using uv)
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# Verify imports
python -c "import ultralytics, cv2, shapely, fastapi, motor"
python -c "import torch; print(torch.__version__)"

# Copy and edit environment config
cp .env.example .env

# Angular dashboard (Phase 6)
cd dashboard
npm install
cd ..
```

## Running the POC

### 1. Start RTSP streams

```bash
./sim/start_streams.sh
```

Launches MediaMTX and loops sample videos into `rtsp://localhost:8554/cam1` and `cam2`.

### 2. Start MongoDB

```bash
mongod --dbpath /path/to/data
```

### 3. Start the backend

```bash
uvicorn backend.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`.

### 4. Start the analytics worker

```bash
python -m analytics.worker
```

### 5. Start the dashboard

```bash
cd dashboard
ng serve
```

Open `http://localhost:4200`.

## Project structure

```
pids-poc/
├── requirements.txt
├── README.md
├── config/
│   ├── cameras.yaml          # RTSP URLs, zones, rules
│   └── settings.py           # Central config (Mongo URI, thresholds, etc.)
├── sim/
│   ├── start_streams.sh      # ffmpeg loop -> RTSP
│   └── samples/              # Sample videos (person, animal)
├── analytics/
│   ├── ingest.py             # RTSP capture + throttle + reconnect
│   ├── detector.py           # YOLOv8 wrapper (CPU)
│   ├── classifier.py         # Threat / non-threat mapping
│   ├── zones.py              # Polygon + point-in-polygon
│   ├── rules.py              # Time-window / suppression
│   ├── events.py             # Snapshot/clip + emit
│   └── worker.py             # Per-camera pipeline orchestrator
├── backend/
│   ├── main.py               # FastAPI app
│   ├── models.py             # Pydantic models
│   ├── schemas.py            # Request/response schemas
│   ├── routes/               # cameras, events, stats, ws
│   └── db.py                 # MongoDB connection + CRUD
├── dashboard/                # Angular 19 SPA
│   └── src/app/
│       ├── components/       # live-view, alert-feed, event-log, stats, config
│       ├── services/         # api, ws, camera
│       └── models/           # TS interfaces
└── media/
    ├── snapshots/
    └── clips/
```

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/cameras` | List cameras + status |
| GET/POST/PUT | `/cameras/{id}/zone` | Read/update detection zone |
| GET/POST/PUT | `/cameras/{id}/rules` | Read/update time-window & suppression rules |
| GET | `/events` | List/filter events (paginated) |
| POST | `/events` | Ingest event from worker |
| GET | `/events/{id}/snapshot` | Serve snapshot image |
| GET | `/events/{id}/clip` | Serve video clip |
| GET | `/stats` | Intrusion/suppression counts per camera |
| WS | `/ws/alerts` | Live alert push |

## Deviations from production spec

| Production spec | POC | Rationale |
|-----------------|-----|-----------|
| YOLOv8 + Darknet | Ultralytics YOLOv8 (PyTorch) | YOLOv8 is PyTorch-native; Darknet runs v1-v4/v7 |
| CUDA 11.7 / RTX 3090 | CPU-only | Target laptop has no NVIDIA GPU |
| 64 GB RAM, multi-server | 15 GB laptop, throttled FPS | Adequate to demonstrate logic |
| .NET Core backend | FastAPI | Per updated parent doc |
| Angular 16 | Angular 19 | Latest LTS |
| 40 cameras | 1-2 simulated | CPU constraint |

## Out of scope (future work)

- CISF-uniform suppression (requires custom-trained classifier)
- IoT / AIR beam-sensor processing (no sensor hardware)
- GPU acceleration and multi-server scale-out
- Email/SMS notification gateways (stubbed as log entries)
- SAN storage and 60-day retention
- Role-based operator access

## Documentation

- [`PIDS_POC_Implementation_Plan.md`](PIDS_POC_Implementation_Plan.md) — Full POC design and specification
- [`PIDS_POC_Implementation_Phases.md`](PIDS_POC_Implementation_Phases.md) — Phase-by-phase breakdown with milestones and acceptance criteria

## License

Proprietary. SAIL-ISP internal use only.
