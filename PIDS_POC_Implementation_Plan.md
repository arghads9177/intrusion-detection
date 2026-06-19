# SAIL-ISP PIDS — POC Implementation Plan

## Intrusion Detection via Video Analytics (CCTV Simulation)

**Parent reference:** `PIDS_Software_AIML_Components.md` (SAIL-ISP/PIDS/TS/001, Rev. 02)
**POC objective:** Demonstrate, on a single developer laptop, an end-to-end video-analytics pipeline that ingests a *simulated* CCTV feed, detects human intrusion across a defined perimeter zone, filters out animal/environmental false alarms, applies after-hours/zone rules, and surfaces alerts through a FastAPI backend, a database, and a web dashboard.

---

## 1. Scope

### 1.1 In Scope (confirmed)

| # | Capability | Source feature in parent doc |
|---|------------|------------------------------|
| 1 | **Human intrusion detection** — detect a person crossing/entering a defined perimeter zone | §4.4, §4.5 |
| 2 | **False-alarm filtering** — distinguish humans from animals/birds/environmental motion | §4.4, §4.3 |
| 3 | **After-hours / zone rules** — time-window logic (e.g. Central Store alerts only outside working hours) and configurable detection zones | §4.5 |
| 4 | **CCTV simulation via RTSP** — re-stream recorded video over a local RTSP server so the pipeline ingests RTSP exactly like a real Dahua camera | §3 |
| 5 | **Full mini-stack** — FastAPI backend + MongoDB + web dashboard (live view, event list, snapshots) | §6, §7 |
| 6 | **Alert generation** — event creation with snapshot + video clip + metadata, surfaced on dashboard and via API | §6 |

### 1.2 Out of Scope (POC) — documented as future work

- **CISF-uniform suppression** — needs a custom-trained classifier + labelled uniform dataset. Deferred (§4.4 future scope).
- **IoT / AIR beam-sensor processing** — no sensor hardware in POC (parent §5). Optionally mockable later.
- **Production hardware** — RTX 3090 / CUDA, multi-server deployment, SAN storage, 60-day retention, email/SMS gateway integration. POC runs CPU-only on one machine.
- **Scale** — production handles ~40 cameras across 3 servers; POC runs **1–2 simulated cameras**.

### 1.3 Deviations from Production Spec (declared for stakeholders)

| Spec requirement | POC implementation | Rationale |
|------------------|--------------------|-----------|
| YOLO v8.0 **+ Darknet** | **Ultralytics YOLOv8** (PyTorch), Darknet omitted | "YOLOv8 on Darknet" is technically inconsistent — YOLOv8 is PyTorch-based; Darknet runs YOLOv1–v4/v7. YOLOv8 detection intent is preserved. |
| CUDA 11.7 / RTX 3090 GPU | **CPU-only inference** | Target laptop (i7-7500U, Intel HD 620, no NVIDIA GPU). GPU is a production-server concern. |
| 64 GB RAM servers | 15 GB laptop, throttled FPS | POC processes a few FPS — adequate to demonstrate logic. |
| PostgreSQL / MongoDB | **MongoDB** | Flexible document schema for events; simpler JSON-native storage. |
| .NET Core backend → **FastAPI** | **FastAPI** | Per updated parent doc §7.1. |
| **Angular 16** dashboard | **Angular 19** | Matches parent doc intent; v19 is latest LTS. SPA consuming FastAPI REST + WebSocket. |

---

## 2. Target Environment

- **Machine:** Intel i7-7500U (2c/4t), 15 GB RAM, Intel HD 620 (no CUDA), Linux.
- **Inference mode:** CPU. Model: `yolov8n` (nano) primary, `yolov8s` optional. Input downscaled (e.g. 640→480). Pipeline throttled to **3–5 FPS** per camera.
- **Expected throughput:** ~1–5 FPS/camera on this CPU — sufficient for POC demonstration.

---

## 3. POC Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         POC (single laptop)                          │
│                                                                      │
│  Sample videos ──► [MediaMTX RTSP server] ──► rtsp://localhost:8554  │
│   (.mp4 looped     (ffmpeg re-stream)              │  cam1, cam2     │
│    via ffmpeg)                                      ▼                 │
│                                          ┌──────────────────────┐    │
│                                          │  Analytics Worker     │    │
│                                          │  (Python)             │    │
│                                          │  1. RTSP ingest (cv2) │    │
│                                          │  2. YOLOv8 detect     │    │
│                                          │  3. Class filter      │    │
│                                          │  4. Zone + rules      │    │
│                                          │  5. Event + snapshot  │    │
│                                          └─────────┬────────────┘    │
│                                                    │ event (HTTP/DB)  │
│                                                    ▼                  │
│                                  ┌──────────────────────────────┐    │
│                                  │  FastAPI backend             │    │
│                                  │  - /events, /alerts, /cameras│    │
│                                  │  - WebSocket live alerts     │    │
│                                  │  - serves snapshots/clips    │    │
│                                  └──────┬──────────────┬────────┘    │
│                                         │              │             │
│                              ┌──────────▼───┐   ┌──────▼─────────┐   │
│                              │ MongoDB      │   │  Web Dashboard │   │
│                              │ events/alerts│   │  (live view,   │   │
│                              │ cameras/zones│   │   events,      │   │
│                              └──────────────┘   │   snapshots)   │   │
│                              media/ (snapshots, └────────────────┘   │
│                                       clips on disk)                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Technology Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| CCTV simulation | **MediaMTX** (RTSP server) + **ffmpeg** (loop re-stream) | Produces real `rtsp://` URLs |
| Video ingest | **OpenCV** (`cv2.VideoCapture` on RTSP) | Matches parent §3 ingest design |
| Detection model | **Ultralytics YOLOv8** (`yolov8n`), CPU/PyTorch | COCO classes incl. person, dog, cat, bird, horse, etc. |
| Tracking (optional) | Ultralytics built-in tracker (ByteTrack) | Stable IDs for line-crossing logic |
| Analytics logic | Python (zone polygons, rules) | Shapely for point-in-polygon |
| Backend API | **FastAPI** + Uvicorn | REST + WebSocket |
| Database | **MongoDB** (PyMongo + Pydantic) | Document-based; flexible schema for events |
| Dashboard | **Angular 19** | REST + WebSocket consumption; TypeScript/SPA |
| Media storage | Local `media/` dir | Snapshots + short clips |
| Packaging | Python venv + local service installs (MongoDB, MediaMTX) | Reproducible setup |

---

## 5. Component Design

### 5.1 CCTV Simulation (RTSP)

- Run **MediaMTX** locally (exposes RTSP on `:8554`).
- Use **ffmpeg** to loop sample perimeter/surveillance videos into RTSP paths:
  `ffmpeg -re -stream_loop -1 -i sample_perimeter.mp4 -c copy -f rtsp rtsp://localhost:8554/cam1`
- Two simulated cameras (`cam1` boundary, `cam2` Central Store) to exercise different zone/time rules.
- **Sample footage:** pedestrian/intruder clips + animal clips (to prove false-alarm filtering). Sourced from free CCTV/surveillance sample datasets.

### 5.2 Ingestion Module

- `cv2.VideoCapture("rtsp://...")` per camera, each in its own worker/thread.
- Frame-rate throttling (process every Nth frame → ~3–5 FPS).
- Reconnect-on-drop loop (parent §3.3 stream management).
- Read-only consumption (mirrors least-privilege "Read" on feeds, parent §3.2).

### 5.3 Detection Engine (YOLOv8)

- Load `yolov8n.pt` once; run `model.predict`/`model.track` per frame on CPU.
- Output: bounding boxes, COCO class, confidence.
- Configurable confidence threshold (default 0.4).
- Classes of interest grouped:
  - **THREAT class:** `person`
  - **NON-THREAT (false-alarm) classes:** `dog, cat, bird, horse, cow, sheep, etc.`

### 5.4 Classification & False-Alarm Filtering

- Map detections to THREAT / NON-THREAT groups.
- Only `person` detections are eligible to raise intrusion alerts.
- Animals/birds are logged (for the demo "we saw it and suppressed it") but **never alerted** — directly demonstrates parent §4.4 false-alarm reduction.

### 5.5 Zone & Intrusion Logic

- Per camera, define a **detection zone** as a polygon (config file / DB; editable later via dashboard).
- For each `person` detection, test whether its anchor point (bottom-center of bbox) is **inside the zone** (Shapely point-in-polygon).
- **Temporal confirmation:** require the person to persist in-zone for **N consecutive processed frames** (e.g. 3) before confirming — avoids single-frame false positives (parent §4.5).
- (Optional) line-crossing via tracker IDs for "crossed the perimeter" semantics.

### 5.6 After-Hours / Zone Rules

- Per-camera rule config: `active_hours` window, `sensitivity`, `suppressed_classes`.
- **Central Store rule:** `cam2` only raises alerts **outside working hours** (e.g. 18:00–08:00) — demonstrates parent §4.5 time-window logic.
- Boundary camera (`cam1`): active 24×7.

### 5.7 Event & Alert Generation

On a confirmed intrusion:
1. Capture **snapshot** (annotated frame with bbox) → `media/snapshots/`.
2. Save a short **video clip** (pre/post buffer, e.g. 5 s) → `media/clips/`.
3. Build event record: camera_id, timestamp, class, confidence, zone_id, bbox, snapshot path, clip path, rule_applied.
4. POST to FastAPI `/events` (or write via shared DB layer).
5. Backend persists to MongoDB and **pushes a live alert** over WebSocket to the dashboard.
6. **De-duplication / cooldown:** suppress repeat alerts for the same track within a cooldown window (e.g. 30 s) to avoid alert storms.

> POC stubs email/SMS as a logged "notification dispatched" action (parent §6.3 gateway is production-only).

### 5.8 FastAPI Backend

Endpoints (indicative):

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/cameras` | List simulated cameras + status |
| GET/POST/PUT | `/cameras/{id}/zone` | Read/update detection zone polygon |
| GET/POST/PUT | `/cameras/{id}/rules` | Read/update time-window & suppression rules |
| GET | `/events` | List/filter intrusion events (paginated) |
| POST | `/events` | Ingest event from analytics worker |
| GET | `/events/{id}/snapshot` | Serve snapshot image |
| GET | `/events/{id}/clip` | Serve video clip |
| GET | `/stats` | Counts: intrusions, suppressed false alarms, per camera |
| WS | `/ws/alerts` | Live alert push to dashboard |

### 5.9 Database Schema (MongoDB)

**Collections:**

- **cameras** — `_id`, `name`, `rtsp_url`, `location_type` (boundary/central_store), `status`, `created_at`.
- **zones** — `_id`, `camera_id`, `polygon` (array of [lat, lon] or [x, y] points), `active`, `created_at`.
- **rules** — `_id`, `camera_id`, `active_hours_start`, `active_hours_end`, `suppressed_classes` (array), `sensitivity`, `created_at`.
- **events** — `_id`, `camera_id`, `timestamp`, `object_class`, `confidence`, `bbox`, `zone_id`, `snapshot_path`, `clip_path`, `rule_applied`, `status` (raised/ack/resolved), `cooldown_until`.
- **suppressed_detections** (optional, for demo metrics) — `_id`, `camera_id`, `timestamp`, `object_class`, `reason` (animal / out-of-hours / out-of-zone), `created_at`.

**Advantages for POC:**
- Flexible schema (no migrations for rule/event changes).
- Native JSON storage of polygon/bbox arrays.
- Scales well for a few cameras and thousands of events.

### 5.10 Dashboard (Angular 19)

Built as a **single-page application (SPA)** consuming the FastAPI REST + WebSocket APIs.

**Components & pages:**
- **Live view:** per-camera annotated MJPEG/WebSocket stream with zone overlay + real-time bboxes (Canvas/SVG).
- **Alert feed:** real-time list (WebSocket-pushed) of new intrusions with thumbnail snapshot and timestamp.
- **Event log:** searchable/filterable table (camera, time, object_class) with snapshot preview, clip playback (video element), and detail modal.
- **Stats dashboard:** intrusions count, suppressed false alarms count, per-camera breakdown (bar/line charts using a charting library like Chart.js or ng-charts).
- **Configuration panel:** edit zone polygons (interactive polygon editor), time-window rules, suppressed classes, sensitivity thresholds. Changes POST back to FastAPI.
- **Camera management:** register/edit RTSP URLs, view status, enable/disable per camera.

**Tech stack:**
- Angular 19, TypeScript, RxJS.
- Angular Material or similar for UI components.
- WebSocket service for live alerts.
- HTTP service for REST endpoints.
- Canvas/SVG annotation layer for zone/bbox overlay.

---

## 6. Data Flow (single intrusion)

1. ffmpeg loops `intruder.mp4` → MediaMTX → `rtsp://localhost:8554/cam1`.
2. Worker reads frame (throttled) → YOLOv8 detects `person` @ 0.82.
3. Class = THREAT; anchor point inside `cam1` zone → candidate.
4. Persists 3 consecutive frames → **confirmed**; cam1 active 24×7 → rule passes.
5. Cooldown check OK → snapshot + 5 s clip saved.
6. Worker POSTs event → FastAPI → MongoDB insert → WebSocket push.
7. Dashboard shows live alert + snapshot; event appears in log; stats increment.
8. An `animal.mp4` on cam2 → detected `dog` → NON-THREAT → logged as suppressed, **no alert**.

---

## 7. Proposed Project Structure

```
pids-poc/
├── requirements.txt
├── README.md
├── config/
│   ├── cameras.yaml           # rtsp urls, zones, rules
│   └── settings.py
├── sim/
│   ├── start_streams.sh       # ffmpeg loop -> rtsp
│   └── samples/               # sample videos (person, animal)
├── analytics/
│   ├── ingest.py              # RTSP capture + throttle + reconnect
│   ├── detector.py            # YOLOv8 wrapper (CPU)
│   ├── classifier.py          # threat / non-threat mapping
│   ├── zones.py               # polygon + point-in-polygon
│   ├── rules.py               # time-window / suppression
│   ├── events.py              # snapshot/clip + emit
│   └── worker.py              # orchestrates the pipeline per camera
├── backend/
│   ├── main.py                # FastAPI app
│   ├── models.py              # Pydantic models for MongoDB
│   ├── schemas.py             # Request/response schemas
│   ├── routes/                # cameras, events, stats, ws
│   └── db.py                  # MongoDB connection + CRUD
├── dashboard/                 # Angular 19 SPA
│   ├── angular.json
│   ├── package.json
│   ├── src/
│   │   ├── app/
│   │   │   ├── components/    # live-view, alert-feed, event-log, stats, config
│   │   │   ├── services/      # api.service, ws.service, camera.service
│   │   │   ├── models/        # TS interfaces (Camera, Event, Zone, etc.)
│   │   │   ├── app.component.ts
│   │   │   └── app.module.ts
│   │   ├── assets/
│   │   ├── index.html
│   │   └── styles.css
│   └── tsconfig.json
└── media/
    ├── snapshots/
    └── clips/
```

---

## 8. Implementation Phases & Milestones

| Phase | Deliverable | Est. effort |
|-------|-------------|-------------|
| **0. Setup** | venv, deps, MongoDB + MediaMTX installed locally, sample videos collected | 0.5 day |
| **1. CCTV simulation** | RTSP streams (`cam1`, `cam2`) live and viewable | 0.5 day |
| **2. Detection pipeline** | RTSP ingest → YOLOv8 CPU → annotated output window | 1 day |
| **3. Filtering + zones + rules** | Threat/non-threat classification, zone polygons, temporal confirm, after-hours rule | 1.5 days |
| **4. Events + storage** | Snapshot/clip capture, MongoDB persistence, dedup/cooldown | 1 day |
| **5. FastAPI backend** | REST + WebSocket endpoints, media serving | 1 day |
| **6. Dashboard** | Live view, alert feed, event log, stats | 1.5 days |
| **7. Integration + demo polish** | End-to-end run, demo script, README, tune thresholds/FPS | 1 day |
| | **Total** | **~8 days** |

---

## 9. Setup & Dependencies (indicative)

**Python backend (`requirements.txt`):**
```
ultralytics            # YOLOv8 (pulls torch CPU build)
opencv-python
shapely
fastapi, uvicorn[standard]
pymongo, motor         # MongoDB async + sync drivers
pydantic
websockets
python-dotenv          # config
```

**Angular frontend (`dashboard/package.json`):**
```
@angular/core, @angular/common, @angular/forms, @angular/router
@angular/platform-browser
typescript
rxjs
chart.js, ng-charts    # stats visualization (optional)
angular-material       # UI components (optional)
```

**System / services:**
```
ffmpeg                 # video streaming
mediamtx               # RTSP server (local binary)
mongodb                # local install (default: localhost:27017)
nodejs 18+             # for Angular build/dev
```

CPU-only torch is the default wheel — no CUDA needed. MongoDB and MediaMTX run as locally installed services.

---

## 10. Testing & Validation (maps to parent §9)

| Test | Method | Pass criterion |
|------|--------|----------------|
| Intrusion detection accuracy | Run person clip through pipeline | Alert raised for in-zone person |
| False-alarm filtering | Run animal/bird clips | **No** alert; logged as suppressed |
| Zone logic | Person outside zone | No alert |
| After-hours rule | cam2 person during working hours vs after hours | Alert only after hours |
| Temporal confirmation | Single-frame flicker detection | No alert on transient |
| Alert delivery | Confirmed intrusion | Event in DB + WebSocket push + dashboard shows snapshot/clip |
| Dedup/cooldown | Continuous presence | One alert per cooldown window, not per frame |
| Performance | Sustained run, 2 cameras | Stable ~3–5 FPS, no memory leak/crash on CPU |

---

## 11. Performance Notes (CPU constraints)

- Use **`yolov8n`** (nano); fall back to `yolov8s` only if accuracy needs it.
- Downscale frames (e.g. 480p) before inference.
- Throttle to every Nth frame (3–5 FPS effective).
- Run inference with `torch.set_num_threads()` tuned to 4.
- Limit to **1–2 cameras** concurrently on this hardware.
- Optional later: ONNX/OpenVINO export for faster CPU inference on Intel iGPU.

---

## 12. Future Scope (beyond POC → toward production)

- **CISF-uniform suppression** (custom-trained classifier on labelled uniform dataset).
- **IoT AIR beam-sensor** ingest + event fusion (parent §5).
- **GPU acceleration** (CUDA/RTX) and scale-out to ~40 cameras across detection servers.
- **Real notification gateways** (email/SMS) and on-site audio speaker trigger.
- **Angular 16 dashboard** and role-based operator access.
- **SAN storage** + 60-day retention; integration with existing NVR.

---

## 13. Open Items / Assumptions

- Sample CCTV footage (person + animal) to be sourced from free surveillance datasets; if you have representative plant footage, it will improve realism.
- MongoDB chosen for flexible document storage of events/zones/rules; switchable to PostgreSQL if preferred.
- Minimal JS dashboard assumed for POC speed; Angular can replace it against the same API.

---

*This plan implements a faithful, runnable subset of `PIDS_Software_AIML_Components.md` focused on video-analytics intrusion detection with simulated CCTV, honestly documenting every deviation from the production specification.*
