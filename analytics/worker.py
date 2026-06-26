"""Phase-2 harness: ingest → detect → annotate → display/save.

Usage:
    python -m analytics.worker --camera cam1
    python -m analytics.worker --camera cam1 --headless      # write annotated frames to disk
    python -m analytics.worker --camera cam1 --url rtsp://...  # override RTSP URL
"""

import argparse
import logging
import time
from pathlib import Path

import cv2
import numpy as np

from analytics.detector import Detection, Detector
from analytics.ingest import FrameIngestor
from config.settings import FPS_THROTTLE, SNAPSHOTS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Colour per class (BGR) — fallback to white
_CLASS_COLOURS: dict[str, tuple[int, int, int]] = {
    "person": (0, 0, 255),
    "dog": (0, 200, 80),
    "cat": (0, 200, 80),
    "bird": (0, 200, 80),
    "horse": (0, 200, 80),
    "cow": (0, 200, 80),
    "sheep": (0, 200, 80),
}
_DEFAULT_COLOUR = (255, 255, 255)


def annotate_frame(
    frame: np.ndarray,
    detections: list[Detection],
    fps: float,
) -> np.ndarray:
    out = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        colour = _CLASS_COLOURS.get(det.class_name, _DEFAULT_COLOUR)
        cv2.rectangle(out, (x1, y1), (x2, y2), colour, 2)
        label = f"{det.class_name} {det.confidence:.2f}"
        if det.track_id is not None:
            label = f"#{det.track_id} {label}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(out, (x1, y1 - th - 6), (x1 + tw + 4, y1), colour, -1)
        cv2.putText(
            out, label, (x1 + 2, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA,
        )

    fps_text = f"FPS: {fps:.1f}"
    cv2.putText(
        out, fps_text, (10, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA,
    )
    return out


def run(camera_id: str, rtsp_url: str | None, headless: bool) -> None:
    detector = Detector()
    ingestor = FrameIngestor(camera_id=camera_id, rtsp_url=rtsp_url, fps=FPS_THROTTLE)

    out_dir: Path | None = None
    if headless:
        out_dir = Path(SNAPSHOTS_DIR) / "worker_preview" / camera_id
        out_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Headless mode — writing annotated frames to %s", out_dir)

    window_title = f"PIDS — {camera_id}"
    if not headless:
        cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)

    frame_count = 0
    fps_start = time.monotonic()
    measured_fps = 0.0

    try:
        for frame_obj in ingestor.stream():
            detections = detector.detect(frame_obj.image)

            # FPS measurement — rolling 30-frame window
            frame_count += 1
            if frame_count % 30 == 0:
                elapsed = time.monotonic() - fps_start
                measured_fps = 30 / elapsed if elapsed > 0 else 0.0
                fps_start = time.monotonic()
                logger.info(
                    "[%s] FPS=%.1f  detections=%d  (%s)",
                    camera_id,
                    measured_fps,
                    len(detections),
                    ", ".join(f"{d.class_name}({d.confidence:.2f})" for d in detections) or "none",
                )

            annotated = annotate_frame(frame_obj.image, detections, measured_fps)

            if headless and out_dir is not None:
                fname = out_dir / f"{frame_count:06d}.jpg"
                cv2.imwrite(str(fname), annotated)
            else:
                cv2.imshow(window_title, annotated)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    logger.info("User quit")
                    break
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        ingestor.release()
        if not headless:
            cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase-2 detection worker")
    parser.add_argument("--camera", default="cam1", help="Camera ID (default: cam1)")
    parser.add_argument("--url", default=None, help="Override RTSP URL")
    parser.add_argument(
        "--headless", action="store_true",
        help="Write annotated frames to disk instead of displaying a window",
    )
    args = parser.parse_args()
    run(camera_id=args.camera, rtsp_url=args.url, headless=args.headless)


if __name__ == "__main__":
    main()
