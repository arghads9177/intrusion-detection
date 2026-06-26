"""YOLOv8 inference wrapper — loads the model once and detects per frame."""

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from config.settings import (
    CONFIDENCE_THRESHOLD,
    FRAME_DOWNSCALE_WIDTH,
    TORCH_NUM_THREADS,
    YOLO_MODEL,
)

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    class_name: str
    confidence: float
    # bbox in (x1, y1, x2, y2) pixel coords on the *original* frame
    bbox: tuple[int, int, int, int]
    track_id: int | None = None


class Detector:
    """Single-model YOLOv8 detector with optional downscale and ByteTrack."""

    def __init__(
        self,
        model_path: str | Path = YOLO_MODEL,
        confidence: float = CONFIDENCE_THRESHOLD,
        downscale_width: int = FRAME_DOWNSCALE_WIDTH,
        num_threads: int = TORCH_NUM_THREADS,
        use_tracker: bool = True,
    ) -> None:
        torch.set_num_threads(num_threads)
        self.confidence = confidence
        self.downscale_width = downscale_width
        self.use_tracker = use_tracker

        logger.info("Loading YOLO model: %s", model_path)
        self.model = YOLO(str(model_path))
        self._class_names: dict[int, str] = self.model.names  # type: ignore[assignment]

        # warm-up pass to absorb first-inference latency
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        self._run_inference(dummy)
        logger.info("Detector ready (conf=%.2f, threads=%d)", confidence, num_threads)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Run inference on *frame* and return detections scaled back to original size."""
        orig_h, orig_w = frame.shape[:2]
        inference_frame, scale_x, scale_y = self._maybe_downscale(frame)

        results = self._run_inference(inference_frame)

        detections: list[Detection] = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for i in range(len(boxes)):
                box = boxes[i]
                conf = float(box.conf[0])
                if conf < self.confidence:
                    continue
                cls_id = int(box.cls[0])
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])

                # scale back to original frame coordinates
                x1 = int(x1 * scale_x)
                y1 = int(y1 * scale_y)
                x2 = int(x2 * scale_x)
                y2 = int(y2 * scale_y)

                # clamp to frame bounds
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(orig_w, x2), min(orig_h, y2)

                track_id: int | None = None
                if self.use_tracker and boxes.id is not None:
                    track_id = int(boxes.id[i])

                detections.append(
                    Detection(
                        class_name=self._class_names.get(cls_id, str(cls_id)),
                        confidence=round(conf, 3),
                        bbox=(x1, y1, x2, y2),
                        track_id=track_id,
                    )
                )
        return detections

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_inference(self, frame: np.ndarray):
        if self.use_tracker:
            return self.model.track(
                frame,
                persist=True,
                conf=self.confidence,
                verbose=False,
            )
        return self.model.predict(
            frame,
            conf=self.confidence,
            verbose=False,
        )

    def _maybe_downscale(
        self, frame: np.ndarray
    ) -> tuple[np.ndarray, float, float]:
        """Return (inference_frame, scale_x, scale_y).  scale_* map inf→orig."""
        orig_h, orig_w = frame.shape[:2]
        if self.downscale_width and orig_w > self.downscale_width:
            scale = self.downscale_width / orig_w
            new_w = self.downscale_width
            new_h = int(orig_h * scale)
            resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            return resized, orig_w / new_w, orig_h / new_h
        return frame, 1.0, 1.0
