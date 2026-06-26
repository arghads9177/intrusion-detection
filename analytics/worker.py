"""Pipeline worker: ingest → detect → classify → zone → temporal → rules → decision.

Usage:
    python -m analytics.worker --camera cam1
    python -m analytics.worker --camera cam1 --headless      # write frames to disk
    python -m analytics.worker --camera cam1 --url rtsp://...  # override RTSP URL
    python -m analytics.worker --camera cam2 --fake-hour 20  # simulate a specific hour
"""

import argparse
import logging
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from analytics.classifier import ThreatLevel, classify
from analytics.detector import Detection, Detector
from analytics.ingest import FrameIngestor
from analytics.rules import CameraRules, evaluate, load_rules
from analytics.zones import ZoneConfig, in_zone, load_zones
from config.settings import (
    FPS_THROTTLE,
    SNAPSHOTS_DIR,
    TEMPORAL_CONFIRM_FRAMES,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# BGR colours for annotation
_COLOUR_CONFIRMED = (0, 0, 255)      # red — confirmed threat
_COLOUR_SUPPRESSED = (0, 165, 255)   # orange — suppressed
_COLOUR_ANIMAL = (0, 200, 80)        # green — non-threat animal
_COLOUR_PENDING = (255, 255, 0)      # cyan — in-zone but not yet confirmed
_COLOUR_ZONE = (0, 255, 200)         # zone polygon outline


# ---------------------------------------------------------------------------
# Temporal confirmation tracker
# ---------------------------------------------------------------------------

class TemporalTracker:
    """Track consecutive in-zone frames per (track_id or synthetic key).

    When a detection has no track_id (tracker disabled), we use the
    class_name as the key — coarse but sufficient for single-object clips.
    """

    def __init__(self, required_frames: int = TEMPORAL_CONFIRM_FRAMES) -> None:
        self.required = required_frames
        # key → consecutive in-zone frame count
        self._counts: dict[str, int] = defaultdict(int)
        # track keys seen this frame (to reset absent ones)
        self._seen_this_frame: set[str] = set()

    def update(self, key: str, in_zone_flag: bool) -> int:
        """Call once per detection per frame.  Returns current consecutive count."""
        self._seen_this_frame.add(key)
        if in_zone_flag:
            self._counts[key] += 1
        else:
            self._counts[key] = 0
        return self._counts[key]

    def is_confirmed(self, key: str) -> bool:
        return self._counts[key] >= self.required

    def end_frame(self, active_keys: set[str]) -> None:
        """Reset counters for keys not seen in the current frame."""
        absent = set(self._counts) - active_keys
        for k in absent:
            self._counts[k] = 0
        self._seen_this_frame.clear()


# ---------------------------------------------------------------------------
# Decision record
# ---------------------------------------------------------------------------

class DecisionResult:
    CONFIRMED = "confirmed"
    SUPPRESSED = "suppressed"
    PENDING = "pending"

    def __init__(
        self,
        detection: Detection,
        status: str,
        reason: str = "",
        consecutive: int = 0,
    ) -> None:
        self.detection = detection
        self.status = status
        self.reason = reason
        self.consecutive = consecutive


# ---------------------------------------------------------------------------
# Per-frame pipeline
# ---------------------------------------------------------------------------

def process_frame(
    detections: list[Detection],
    zone: ZoneConfig | None,
    rules: CameraRules | None,
    tracker: TemporalTracker,
    fake_now: datetime | None = None,
) -> list[DecisionResult]:
    """Apply classify → zone → rules → temporal to a list of detections.

    Returns one DecisionResult per detection.
    """
    results: list[DecisionResult] = []
    active_keys: set[str] = set()

    for det in detections:
        level = classify(det.class_name)

        # Non-threat animals: suppress immediately, no zone/temporal check
        if level == ThreatLevel.NON_THREAT:
            results.append(DecisionResult(det, DecisionResult.SUPPRESSED, "animal"))
            continue

        # IGNORE class (vehicles, furniture, etc.) — skip entirely
        if level == ThreatLevel.IGNORE:
            continue

        # --- THREAT (person) path ---

        # Rule check (class suppression + time window)
        if rules:
            reason = evaluate(det.class_name, rules, fake_now)
            if reason:
                results.append(DecisionResult(det, DecisionResult.SUPPRESSED, reason))
                continue

        # Zone check
        zone_hit = zone is None or in_zone(det.bbox, zone)
        if not zone_hit:
            results.append(DecisionResult(det, DecisionResult.SUPPRESSED, "out_of_zone"))
            continue

        # Temporal confirmation
        key = str(det.track_id) if det.track_id is not None else det.class_name
        active_keys.add(key)
        count = tracker.update(key, in_zone_flag=True)

        if tracker.is_confirmed(key):
            results.append(DecisionResult(det, DecisionResult.CONFIRMED, consecutive=count))
        else:
            results.append(DecisionResult(det, DecisionResult.PENDING, consecutive=count))

    tracker.end_frame(active_keys)
    return results


# ---------------------------------------------------------------------------
# Annotation
# ---------------------------------------------------------------------------

def annotate_frame(
    frame: np.ndarray,
    results: list[DecisionResult],
    zone: ZoneConfig | None,
    fps: float,
) -> np.ndarray:
    out = frame.copy()

    # Draw zone polygon
    if zone is not None:
        pts = np.array(
            [[int(x), int(y)] for x, y in zone.polygon.exterior.coords[:-1]],
            dtype=np.int32,
        )
        cv2.polylines(out, [pts], isClosed=True, color=_COLOUR_ZONE, thickness=2)

    for r in results:
        x1, y1, x2, y2 = r.detection.bbox
        if r.status == DecisionResult.CONFIRMED:
            colour = _COLOUR_CONFIRMED
        elif r.status == DecisionResult.PENDING:
            colour = _COLOUR_PENDING
        elif r.detection.class_name in {"dog", "cat", "bird", "horse", "cow", "sheep"}:
            colour = _COLOUR_ANIMAL
        else:
            colour = _COLOUR_SUPPRESSED

        cv2.rectangle(out, (x1, y1), (x2, y2), colour, 2)

        parts = [r.detection.class_name, f"{r.detection.confidence:.2f}"]
        if r.detection.track_id is not None:
            parts.insert(0, f"#{r.detection.track_id}")
        if r.reason:
            parts.append(f"[{r.reason}]")
        elif r.status == DecisionResult.PENDING:
            parts.append(f"[{r.consecutive}/{TEMPORAL_CONFIRM_FRAMES}]")
        label = " ".join(parts)

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(out, (x1, y1 - th - 6), (x1 + tw + 4, y1), colour, -1)
        cv2.putText(
            out, label, (x1 + 2, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA,
        )

    cv2.putText(
        out, f"FPS: {fps:.1f}", (10, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA,
    )
    return out


# ---------------------------------------------------------------------------
# Main run loop
# ---------------------------------------------------------------------------

def run(
    camera_id: str,
    rtsp_url: str | None,
    headless: bool,
    fake_hour: int | None,
) -> None:
    zones = load_zones()
    all_rules = load_rules()

    zone = zones.get(camera_id)
    rules = all_rules.get(camera_id)
    tracker = TemporalTracker()
    detector = Detector()
    ingestor = FrameIngestor(camera_id=camera_id, rtsp_url=rtsp_url, fps=FPS_THROTTLE)

    fake_now: datetime | None = None
    if fake_hour is not None:
        fake_now = datetime.now().replace(hour=fake_hour, minute=0, second=0)
        logger.info("Clock override: treating current hour as %02d:00", fake_hour)

    out_dir: Path | None = None
    if headless:
        out_dir = Path(SNAPSHOTS_DIR) / "worker_preview" / camera_id
        out_dir.mkdir(parents=True, exist_ok=True)

    window_title = f"PIDS — {camera_id}"
    if not headless:
        cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)

    frame_count = 0
    fps_start = time.monotonic()
    measured_fps = 0.0

    try:
        for frame_obj in ingestor.stream():
            raw_detections = detector.detect(frame_obj.image)
            decisions = process_frame(raw_detections, zone, rules, tracker, fake_now)

            frame_count += 1
            if frame_count % 30 == 0:
                elapsed = time.monotonic() - fps_start
                measured_fps = 30 / elapsed if elapsed > 0 else 0.0
                fps_start = time.monotonic()

                confirmed = [r for r in decisions if r.status == DecisionResult.CONFIRMED]
                suppressed = [r for r in decisions if r.status == DecisionResult.SUPPRESSED]
                logger.info(
                    "[%s] FPS=%.1f  confirmed=%d  suppressed=%d",
                    camera_id, measured_fps, len(confirmed), len(suppressed),
                )
                for r in confirmed:
                    logger.info(
                        "  CONFIRMED: %s conf=%.2f consecutive=%d",
                        r.detection.class_name, r.detection.confidence, r.consecutive,
                    )
                for r in suppressed:
                    logger.info(
                        "  SUPPRESSED: %s reason=%s",
                        r.detection.class_name, r.reason,
                    )

            annotated = annotate_frame(frame_obj.image, decisions, zone, measured_fps)

            if headless and out_dir is not None:
                cv2.imwrite(str(out_dir / f"{frame_count:06d}.jpg"), annotated)
            else:
                cv2.imshow(window_title, annotated)
                if (cv2.waitKey(1) & 0xFF) == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        ingestor.release()
        if not headless:
            cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser(description="PIDS detection worker (Phase 3)")
    parser.add_argument("--camera", default="cam1", help="Camera ID")
    parser.add_argument("--url", default=None, help="Override RTSP URL")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--fake-hour", type=int, default=None,
        help="Override current hour (0-23) for time-window testing",
    )
    args = parser.parse_args()
    run(
        camera_id=args.camera,
        rtsp_url=args.url,
        headless=args.headless,
        fake_hour=args.fake_hour,
    )


if __name__ == "__main__":
    main()
