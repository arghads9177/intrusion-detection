# SAIL-ISP PIDS POC — Implementation Phases & Milestones

**Companion to:** `PIDS_POC_Implementation_Plan.md`
**Parent reference:** `PIDS_Software_AIML_Components.md` (SAIL-ISP/PIDS/TS/001, Rev. 02)
**Purpose:** Break the POC into self-contained, sequentially buildable phases. Each phase below carries its own specification, step list, deliverables, and acceptance criteria so it can be implemented and verified in isolation before the next phase begins.

---

## Conventions used in this document

- **Goal** — what the phase proves / produces.
- **Prerequisites** — phases or artifacts that must exist first.
- **Specification** — the concrete contract: files, configs, interfaces, and behaviour the phase must satisfy.
- **Steps** — ordered implementation actions.
- **Deliverables** — tangible outputs committed at phase end.
- **Acceptance criteria (Milestone exit)** — objective checks that close the phase.
- **Risks / Notes** — known pitfalls and mitigations.

**Global decisions (carried across all phases):**
- **Database = MongoDB** (per stack §4 / schema §5.9).
- **Inference = CPU only**, `yolov8n`, throttled to 3–5 FPS, 1–2 cameras.
- **Repo root = `pids-poc/`** per the proposed structure in plan §7.

**Dependency chain:** `0 → 1 → 2 → 3 → 4 → 5 → 6 → 7`. Phases 5 (backend) and 6 (dashboard) overlap once the API contract is frozen at the end of Phase 5's spec.

---

## Phase 0 — Environment & Project Scaffolding

**Goal:** A reproducible local environment and an empty-but-wired project skeleton so every later phase has a home.

**Prerequisites:** None.

### Specification
- Python venv (3.10+) with `requirements.txt` from plan §9 pinned to working versions.
- Locally installed services: **MongoDB** (`localhost:27017`), **MediaMTX** (RTSP on `:8554`), **ffmpeg**, **Node.js 18+**.
- Directory tree created exactly as plan §7 (`config/`, `sim/`, `analytics/`, `backend/`, `dashboard/`, `media/snapshots/`, `media/clips/`).
- `config/settings.py` centralizes: Mongo URI, RTSP base URL, media paths, FPS throttle, confidence threshold, `torch` thread count.
- `config/cameras.yaml` seeded with two cameras (`cam1` boundary, `cam2` central_store) including placeholder zones and rules.
- `.env` + `python-dotenv` for environment-specific overrides; `.gitignore` excludes `media/`, `.env`, model weights, `node_modules/`.

### Steps
1. Create repo structure and `README.md` skeleton.
2. Create venv; install Python deps; verify CPU torch wheel (`python -c "import torch; print(torch.__version__)"`).
3. Install + smoke-test MongoDB (`mongosh` ping), MediaMTX (binary runs), ffmpeg (`ffmpeg -version`), Node.
4. Write `config/settings.py` and `config/cameras.yaml` with documented defaults.
5. Pre-download `yolov8n.pt` weights into a cached location.
6. Commit scaffolding.

### Deliverables
`requirements.txt`, project tree, `config/settings.py`, `config/cameras.yaml`, `.env.example`, `.gitignore`, `README.md` (setup section), cached `yolov8n.pt`.

### Acceptance criteria (Milestone 0)
- Fresh `pip install -r requirements.txt` succeeds on CPU-only machine.
- All four system services respond to their smoke tests.
- `python -c "import ultralytics, cv2, shapely, fastapi, motor"` imports clean.

### Risks / Notes
- Torch may try to pull a CUDA wheel — explicitly use the CPU index URL.
- MediaMTX version/config format drift — pin a known release.

---

## Phase 1 — CCTV Simulation (RTSP)

**Goal:** Two looping `rtsp://localhost:8554/cam1|cam2` streams that behave like real Dahua feeds.

**Prerequisites:** Phase 0.

### Specification
- `sim/start_streams.sh` launches MediaMTX (if not running) and one ffmpeg loop per camera.
- ffmpeg command per plan §5.1: `ffmpeg -re -stream_loop -1 -i <sample> -c copy -f rtsp rtsp://localhost:8554/<cam>`.
- `sim/samples/` holds at least: one person/intruder clip, one animal clip, one "empty/no-threat" clip.
- Streams must be continuous (loop seamlessly) and survive client disconnect/reconnect.

### Steps
1. Source/copy sample footage (person, animal, empty) into `sim/samples/`.
2. Write `start_streams.sh` (start MediaMTX → start ffmpeg loops → trap for clean shutdown).
3. Map `cam1` → intruder/perimeter clip, `cam2` → mixed/central-store clip.
4. Verify each stream with `ffplay rtsp://localhost:8554/cam1` (or VLC).
5. Document start/stop in `README.md`.

### Deliverables
`sim/start_streams.sh`, `sim/samples/*`, README run instructions.

### Acceptance criteria (Milestone 1)
- Both RTSP URLs open in an external player and loop indefinitely.
- A player can disconnect and reconnect without restarting the script.

### Risks / Notes
- `-c copy` requires codec compatibility with RTSP; re-encode (`-c:v libx264`) if copy fails.
- Keep sample clips short and CC-licensed; record provenance in README.

---

## Phase 2 — Detection Pipeline (Ingest → YOLOv8 → Annotated Output)

**Goal:** Read an RTSP stream, run CPU YOLOv8, and display annotated detections — the perception core, no business logic yet.

**Prerequisites:** Phases 0–1.

### Specification
- `analytics/ingest.py`: per-camera `cv2.VideoCapture` with frame-throttle (process every Nth frame → 3–5 FPS) and reconnect-on-drop loop (parent §3.3).
- `analytics/detector.py`: loads `yolov8n.pt` once; `predict`/`track` per frame; returns list of `{class, confidence, bbox}`; respects configurable confidence threshold (default 0.4) and `torch.set_num_threads(4)`.
- Optional frame downscale (e.g. 640→480) before inference.
- A runnable harness draws boxes + labels and shows a window (or writes annotated frames to disk for headless runs).

### Steps
1. Implement `ingest.py` capture loop with throttling + reconnect.
2. Implement `detector.py` wrapper (single model load, batch-of-one inference).
3. Wire a temporary `worker.py` entry: ingest → detect → annotate → display.
4. Tune thread count + downscale; measure FPS.
5. Validate `person` and animal detections appear correctly.

### Deliverables
`analytics/ingest.py`, `analytics/detector.py`, initial `analytics/worker.py`, measured FPS note in README.

### Acceptance criteria (Milestone 2)
- Live annotated output for `cam1` shows correct boxes/classes/confidence.
- Sustained ~3–5 FPS per camera on the target CPU.
- Stream drop triggers automatic reconnect without crash.

### Risks / Notes
- First inference is slow (model warm-up) — warm up before timing.
- RTSP latency/buffering: set `cv2` buffer size low; drop stale frames.

---

## Phase 3 — Filtering, Zones & Rules

**Goal:** Turn raw detections into *confirmed, in-zone, in-policy* intrusion candidates while suppressing animals and out-of-hours/out-of-zone cases.

**Prerequisites:** Phase 2.

### Specification
- `analytics/classifier.py`: maps COCO classes → THREAT (`person`) vs NON-THREAT (`dog, cat, bird, horse, cow, sheep, …`). Only `person` is alert-eligible (plan §5.4).
- `analytics/zones.py`: loads polygon per camera; Shapely point-in-polygon on bbox **bottom-center anchor** (plan §5.5).
- **Temporal confirmation:** person must persist in-zone for **N consecutive processed frames** (default 3) before "confirmed" (plan §5.5). Optional tracker-ID line-crossing.
- `analytics/rules.py`: per-camera `active_hours`, `sensitivity`, `suppressed_classes`. `cam2` alerts only outside working hours (e.g. 18:00–08:00); `cam1` is 24×7 (plan §5.6).
- Suppressed events tagged with reason (`animal` / `out-of-hours` / `out-of-zone`) for metrics.

### Steps
1. Implement `classifier.py` THREAT/NON-THREAT grouping.
2. Implement `zones.py` polygon loading + anchor-point test.
3. Add temporal confirmation counter (per track/region) in `worker.py`.
4. Implement `rules.py` time-window + suppression evaluation.
5. Integrate into `worker.py`: detect → classify → zone test → temporal confirm → rule check → candidate/suppressed decision (log only, no DB yet).
6. Unit-test each stage with crafted inputs (point in/out of polygon; in/out of hours; single-frame flicker).

### Deliverables
`analytics/classifier.py`, `analytics/zones.py`, `analytics/rules.py`, updated `worker.py`, unit tests for zone/rule/temporal logic.

### Acceptance criteria (Milestone 3)
- In-zone person held 3 frames → "confirmed" log entry.
- Animal clip → "suppressed: animal", never confirmed.
- Person outside polygon → "suppressed: out-of-zone".
- `cam2` person during working hours → "suppressed: out-of-hours"; same person after hours → confirmed.
- Single-frame flicker → no confirmation.

### Risks / Notes
- Without tracking, temporal confirmation is approximate — start with ByteTrack IDs if line-crossing matters.
- Define zone polygon coordinate space (pixel coords on the downscaled frame) explicitly to avoid scale bugs.

---

## Phase 4 — Event & Alert Generation + Storage

**Goal:** On a confirmed intrusion, persist a rich event with snapshot + clip, with de-duplication/cooldown — independent of the API.

**Prerequisites:** Phase 3. (Mongo collections per plan §5.9.)

### Specification
- `analytics/events.py`:
  - Save **annotated snapshot** → `media/snapshots/` (plan §5.7).
  - Save **short clip** with pre/post buffer (~5 s) → `media/clips/` (maintain a rolling frame buffer).
  - Build event record: `camera_id, timestamp, object_class, confidence, bbox, zone_id, snapshot_path, clip_path, rule_applied, status='raised', cooldown_until`.
  - **Cooldown/dedup:** suppress repeat alerts for the same track/zone within a window (default 30 s) (plan §5.7).
  - Email/SMS stubbed as a logged "notification dispatched" line.
- `backend/db.py` (shared layer): Mongo connection + CRUD for `cameras, zones, rules, events, suppressed_detections` (plan §5.9). Usable by both worker and API.
- Worker writes events via this shared DB layer (HTTP POST path added in Phase 5).

### Steps
1. Implement Mongo `db.py` connection + collection accessors + indexes (e.g. `events.timestamp`, `events.camera_id`).
2. Implement rolling frame buffer for pre-event clip; snapshot annotation.
3. Implement `events.py` record builder + cooldown logic.
4. Persist confirmed events; persist suppressed detections with reason.
5. Seed `cameras`, `zones`, `rules` collections from `config/cameras.yaml`.
6. Integration-test: run intruder clip → exactly one event per cooldown window with valid media paths.

### Deliverables
`analytics/events.py`, `backend/db.py`, seeded Mongo collections, saved snapshots/clips, integration test.

### Acceptance criteria (Milestone 4)
- Confirmed intrusion writes one `events` doc with existing, openable snapshot + clip files.
- Continuous presence yields one event per cooldown window (not per frame).
- Animal/out-of-hours cases land in `suppressed_detections`, not `events`.

### Risks / Notes
- Clip buffering on CPU is memory-sensitive — cap buffer length; write async.
- Ensure media paths stored relative so the API can serve them portably.

---

## Phase 5 — FastAPI Backend (REST + WebSocket + Media Serving)

**Goal:** Expose the data and live alerts through a stable API contract that the dashboard (Phase 6) and worker consume.

**Prerequisites:** Phase 4 (DB layer + event model).

### Specification — API contract (freeze at end of phase; plan §5.8)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/cameras` | List cameras + status |
| GET/POST/PUT | `/cameras/{id}/zone` | Read/update zone polygon |
| GET/POST/PUT | `/cameras/{id}/rules` | Read/update time-window & suppression rules |
| GET | `/events` | List/filter events (paginated; filters: camera, time, class) |
| POST | `/events` | Ingest event from worker |
| GET | `/events/{id}/snapshot` | Serve snapshot image |
| GET | `/events/{id}/clip` | Serve clip |
| GET | `/stats` | Counts: intrusions, suppressed, per camera |
| WS | `/ws/alerts` | Live alert push |

- `backend/main.py` FastAPI app + Uvicorn; `models.py` (Pydantic ↔ Mongo), `schemas.py` (request/response), `routes/` (cameras, events, stats, ws).
- `POST /events` triggers a **WebSocket broadcast** on `/ws/alerts`.
- CORS enabled for the Angular dev origin.
- Static/streamed serving of snapshots & clips.

### Steps
1. Build Pydantic models + request/response schemas.
2. Implement camera/zone/rule routes (read + update) backed by `db.py`.
3. Implement events routes (list/filter/paginate, ingest, media serving).
4. Implement `/stats` aggregation (intrusions vs suppressed, per camera).
5. Implement `/ws/alerts` manager; broadcast on event ingest.
6. Repoint worker's `events.py` to POST to `/events` (DB write now via API).
7. Enable CORS; document contract in README / OpenAPI.

### Deliverables
`backend/main.py`, `models.py`, `schemas.py`, `routes/*`, WebSocket manager, OpenAPI docs, frozen API contract.

### Acceptance criteria (Milestone 5)
- All endpoints return correct data via OpenAPI `/docs` / curl.
- Worker `POST /events` persists and pushes a WS message received by a test client.
- Snapshot/clip endpoints serve openable media.
- Zone/rule updates persist and are reflected on next read.

### Risks / Notes
- Keep WS payload schema identical to event schema to simplify the dashboard.
- Decide whether worker writes via API (chosen) or directly to DB — be consistent to avoid double-writes.

---

## Phase 6 — Dashboard (Angular 19 SPA)

**Goal:** Operator-facing UI: live view, real-time alerts, event log, stats, and config — all against the Phase 5 contract.

**Prerequisites:** Phase 5 (frozen API contract).

### Specification (plan §5.10)
- Angular 19 + TypeScript + RxJS; Angular Material; Chart.js/ng-charts for stats.
- Services: `api.service` (REST), `ws.service` (live alerts), `camera.service`.
- TS interfaces mirror backend schemas (`Camera, Event, Zone, Rule, Stats`).
- Components/pages:
  - **Live view** — per-camera annotated stream (MJPEG/WS) with zone + bbox overlay (Canvas/SVG).
  - **Alert feed** — WS-pushed real-time list with thumbnail + timestamp.
  - **Event log** — searchable/filterable table; snapshot preview; clip playback; detail modal.
  - **Stats dashboard** — intrusions vs suppressed; per-camera charts.
  - **Configuration panel** — interactive zone-polygon editor, time-window rules, suppressed classes, sensitivity → POST back.
  - **Camera management** — register/edit RTSP URLs, status, enable/disable.

### Steps
1. Scaffold Angular 19 app; add Material + charts; configure proxy to FastAPI.
2. Generate TS models from the API contract; build `api.service` + `ws.service`.
3. Build Alert feed (WS) and Event log (REST) first — fastest demo value.
4. Build Stats dashboard from `/stats`.
5. Build Live view overlay (zone + bboxes).
6. Build Configuration panel (zone editor + rules) wired to PUT/POST.
7. Build Camera management page.

### Deliverables
`dashboard/` Angular app: services, models, six components, build config.

### Acceptance criteria (Milestone 6)
- New intrusion appears in the alert feed in real time (WS) with snapshot.
- Event log filters by camera/time/class; opens snapshot + plays clip.
- Stats show correct intrusion vs suppressed counts per camera.
- Editing a zone/rule in the UI persists (verified via API re-read).

### Risks / Notes
- Live annotated streaming on CPU is the heaviest item — fall back to periodic snapshot refresh if MJPEG/WS video is too costly.
- Lock the WS message schema before deep UI work to avoid rework.

---

## Phase 7 — Integration, Validation & Demo Polish

**Goal:** Prove the full pipeline end-to-end against the parent test matrix and package a repeatable demo.

**Prerequisites:** Phases 0–6.

### Specification — must satisfy plan §10 test matrix
| Test | Pass criterion |
|------|----------------|
| Intrusion detection | Alert raised for in-zone person |
| False-alarm filtering | No alert for animal; logged suppressed |
| Zone logic | Person outside zone → no alert |
| After-hours rule | `cam2` alert only after hours |
| Temporal confirmation | No alert on single-frame flicker |
| Alert delivery | Event in DB + WS push + dashboard snapshot/clip |
| Dedup/cooldown | One alert per cooldown window |
| Performance | Stable 3–5 FPS, 2 cameras, no leak/crash |

### Steps
1. Single-command (or documented) startup: streams → worker(s) → backend → dashboard.
2. Execute every §10 test; record results in a validation table.
3. Tune confidence threshold, FPS, cooldown, temporal-N for clean demo behaviour.
4. Soak test (sustained 2-camera run) for memory/stability.
5. Write demo script (intruder → alert; animal → suppressed; after-hours toggle).
6. Finalize `README.md`: setup, run, demo, known limitations, deviations (plan §1.3).

### Deliverables
Startup script/instructions, filled validation results table, demo script, complete README, tuned config defaults.

### Acceptance criteria (Milestone 7 — POC complete)
- Every §10 test passes and is recorded.
- Clean end-to-end demo runnable from documented steps on the target laptop.
- No crash/memory leak over the soak run.

### Risks / Notes
- Time-window test needs a way to simulate "after hours" — add a config/clock override for the demo.
- Keep a fallback (pre-recorded run) in case of live-demo hardware hiccups.

---

## Milestone summary

| Milestone | Phase | Exit signal | Est. effort |
|-----------|-------|-------------|-------------|
| M0 | Setup | Deps + services smoke-tested | 0.5 day |
| M1 | CCTV sim | Two RTSP streams loop & reconnect | 0.5 day |
| M2 | Detection | Annotated output @ 3–5 FPS | 1 day |
| M3 | Filter/zone/rules | Confirm/suppress logic correct | 1.5 days |
| M4 | Events/storage | Event + media + cooldown persisted | 1 day |
| M5 | Backend | API contract frozen; WS push works | 1 day |
| M6 | Dashboard | Live alerts + log + stats + config | 1.5 days |
| M7 | Integration | §10 matrix passes; demo ready | 1 day |
| | **Total** | | **~8 days** |

---

## Cross-phase tracking checklist

- [ ] M0 Environment & scaffolding
- [ ] M1 RTSP simulation
- [ ] M2 Detection pipeline
- [ ] M3 Filtering, zones, rules
- [ ] M4 Events & storage
- [ ] M5 FastAPI backend
- [ ] M6 Angular dashboard
- [ ] M7 Integration & demo
