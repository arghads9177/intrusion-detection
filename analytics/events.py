"""Event and alert generation: cooldown, snapshot, clip, and DB persistence.

Phase 4: worker writes directly to MongoDB via backend.db.
Phase 5: this path will be replaced with POST /events.

Frame flow
----------
  worker.run() calls event_manager.feed_frame(raw_frame) every processed frame.
  On a confirmed detection, worker calls event_manager.on_confirmed(annotated_frame).
  Snapshot = annotated frame at moment of event.
  Clip     = pre-buffer raw frames + post-buffer raw frames written by feed_frame.
"""

import logging
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

import config.settings as _settings
from analytics.detector import Detection
from backend.db import ensure_indexes, insert_event, insert_suppressed, seed_from_config

logger = logging.getLogger(__name__)

_PRE_SECONDS = 5
_POST_SECONDS = 5

# Exported so tests can compute expected frame counts
_PRE_FRAMES: int = _PRE_SECONDS * _settings.FPS_THROTTLE
_POST_FRAMES: int = _POST_SECONDS * _settings.FPS_THROTTLE


# ---------------------------------------------------------------------------
# Clip writer
# ---------------------------------------------------------------------------


class _ClipWriter:
    """Writes pre-buffered frames then up to post_count subsequent frames."""

    def __init__(
        self,
        path: Path,
        pre_frames: list[np.ndarray],
        fps: float,
        post_count: int,
    ) -> None:
        self.path = path
        self._remaining = post_count
        self._done = False

        path.parent.mkdir(parents=True, exist_ok=True)

        h, w = (pre_frames[0].shape[:2] if pre_frames else (480, 640))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
        self._writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))

        for frame in pre_frames:
            self._writer.write(frame)

    def feed(self, frame: np.ndarray) -> None:
        if self._done:
            return
        self._writer.write(frame)
        self._remaining -= 1
        if self._remaining <= 0:
            self._finalize()

    def _finalize(self) -> None:
        self._writer.release()
        self._done = True
        logger.debug("Clip finalised: %s", self.path)

    def close(self) -> None:
        if not self._done:
            self._finalize()

    @property
    def done(self) -> bool:
        return self._done


# ---------------------------------------------------------------------------
# Event manager
# ---------------------------------------------------------------------------


class EventManager:
    """Manages snapshot/clip storage, cooldown tracking, and DB writes.

    One instance per worker/camera.
    """

    def __init__(
        self,
        camera_id: str,
        fps: float | None = None,
        db_name: str | None = None,
    ) -> None:
        self.camera_id = camera_id
        # Capture settings at init time so test fixtures can patch them first
        self.fps = fps if fps is not None else float(_settings.FPS_THROTTLE)
        self._cooldown_seconds = _settings.COOLDOWN_SECONDS
        self._snapshots_dir = Path(_settings.SNAPSHOTS_DIR)
        self._clips_dir = Path(_settings.CLIPS_DIR)
        self._db_name_override = db_name

        self._pre_buffer: deque[np.ndarray] = deque(
            maxlen=_PRE_SECONDS * _settings.FPS_THROTTLE
        )
        self._clip_writers: list[_ClipWriter] = []

        # key → cooldown_until (UTC)
        self._event_cooldowns: dict[str, datetime] = {}
        self._suppressed_cooldowns: dict[str, datetime] = {}

        self._snapshots_dir.mkdir(parents=True, exist_ok=True)
        self._clips_dir.mkdir(parents=True, exist_ok=True)

        kw: dict[str, Any] = {}
        if db_name:
            kw["db_name"] = db_name
        ensure_indexes(**kw)
        seed_from_config(**kw)

    # ------------------------------------------------------------------
    # Per-frame feed (must be called every processed frame)
    # ------------------------------------------------------------------

    def feed_frame(self, frame: np.ndarray) -> None:
        """Append raw frame to pre-buffer and advance all active clip writers."""
        self._pre_buffer.append(frame.copy())
        done: list[_ClipWriter] = []
        for cw in self._clip_writers:
            cw.feed(frame)
            if cw.done:
                done.append(cw)
        for cw in done:
            self._clip_writers.remove(cw)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_confirmed(
        self,
        detection: Detection,
        zone_id: str,
        annotated_frame: np.ndarray,
        rule_applied: str = "",
    ) -> bool:
        """Handle a confirmed intrusion.

        Returns True if an event was persisted, False if cooldown suppressed it.
        """
        track_key = str(detection.track_id) if detection.track_id is not None else detection.class_name
        cooldown_key = f"{self.camera_id}:{zone_id}:{track_key}"
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if cooldown_key in self._event_cooldowns and now < self._event_cooldowns[cooldown_key]:
            logger.debug("Event cooldown active — skipping: %s", cooldown_key)
            return False

        event_id = uuid.uuid4().hex[:12]
        ts_str = now.strftime("%Y%m%d_%H%M%S")
        cam = self.camera_id

        # --- snapshot ---
        snapshot_rel = f"{cam}/{ts_str}_{event_id}.jpg"
        snapshot_abs = self._snapshots_dir / snapshot_rel
        snapshot_abs.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(snapshot_abs), annotated_frame)

        # --- clip ---
        clip_rel = f"{cam}/{ts_str}_{event_id}.mp4"
        clip_abs = self._clips_dir / clip_rel
        cw = _ClipWriter(
            path=clip_abs,
            pre_frames=list(self._pre_buffer),
            fps=self.fps,
            post_count=_POST_SECONDS * _settings.FPS_THROTTLE,
        )
        self._clip_writers.append(cw)

        # --- cooldown ---
        cooldown_until = now + timedelta(seconds=self._cooldown_seconds)
        self._event_cooldowns[cooldown_key] = cooldown_until

        # --- DB record ---
        doc: dict[str, Any] = {
            "camera_id": self.camera_id,
            "timestamp": now,
            "object_class": detection.class_name,
            "confidence": detection.confidence,
            "bbox": list(detection.bbox),
            "zone_id": zone_id,
            "track_id": detection.track_id,
            "snapshot_path": snapshot_rel,
            "clip_path": clip_rel,
            "rule_applied": rule_applied,
            "status": "raised",
            "cooldown_until": cooldown_until,
        }
        kw: dict[str, Any] = {}
        if self._db_name_override:
            kw["db_name"] = self._db_name_override
        inserted_id = insert_event(doc, **kw)

        logger.info(
            "EVENT raised  camera=%s  class=%s  conf=%.2f  id=%s  snapshot=%s",
            self.camera_id,
            detection.class_name,
            detection.confidence,
            inserted_id,
            snapshot_rel,
        )
        # Notification stub — will be replaced with real dispatch in a later phase
        logger.info(
            "[NOTIFICATION] Alert dispatched  event_id=%s  camera=%s",
            inserted_id,
            self.camera_id,
        )
        return True

    def on_suppressed(self, detection: Detection, reason: str) -> None:
        """Persist a suppressed detection (once per cooldown window to avoid DB spam)."""
        cooldown_key = f"supp:{self.camera_id}:{reason}:{detection.class_name}"
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if cooldown_key in self._suppressed_cooldowns and now < self._suppressed_cooldowns[cooldown_key]:
            return

        self._suppressed_cooldowns[cooldown_key] = now + timedelta(seconds=self._cooldown_seconds)

        doc: dict[str, Any] = {
            "camera_id": self.camera_id,
            "timestamp": now,
            "object_class": detection.class_name,
            "confidence": detection.confidence,
            "bbox": list(detection.bbox),
            "reason": reason,
        }
        kw: dict[str, Any] = {}
        if self._db_name_override:
            kw["db_name"] = self._db_name_override
        insert_suppressed(doc, **kw)
        logger.debug(
            "SUPPRESSED logged  camera=%s  class=%s  reason=%s",
            self.camera_id,
            detection.class_name,
            reason,
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        for cw in self._clip_writers:
            cw.close()
        self._clip_writers.clear()
