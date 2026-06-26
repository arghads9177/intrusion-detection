"""RTSP frame ingestor with throttling and auto-reconnect."""

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass

import cv2
import numpy as np

from config.settings import FPS_THROTTLE, RTSP_BASE_URL

logger = logging.getLogger(__name__)

RECONNECT_DELAY = 5  # seconds between reconnect attempts
CAP_BUFFER_SIZE = 1  # keep only latest frame in buffer


@dataclass
class Frame:
    camera_id: str
    image: np.ndarray
    timestamp: float


class FrameIngestor:
    """Yields throttled frames from a single RTSP camera with auto-reconnect."""

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str | None = None,
        fps: int = FPS_THROTTLE,
    ) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url or f"{RTSP_BASE_URL}/{camera_id}"
        self.fps = max(1, fps)
        self._cap: cv2.VideoCapture | None = None

    def _open(self) -> bool:
        if self._cap is not None:
            self._cap.release()
        cap = cv2.VideoCapture(self.rtsp_url)
        # keep the internal buffer small so we always read the latest frame
        cap.set(cv2.CAP_PROP_BUFFERSIZE, CAP_BUFFER_SIZE)
        if cap.isOpened():
            self._cap = cap
            logger.info("Opened stream: %s", self.rtsp_url)
            return True
        cap.release()
        logger.warning("Could not open stream: %s", self.rtsp_url)
        return False

    def stream(self, max_failures: int = 0) -> Iterator[Frame]:
        """Yield frames indefinitely.  max_failures=0 means retry forever."""
        failures = 0
        interval = 1.0 / self.fps
        last_yield_time = 0.0

        while True:
            if self._cap is None or not self._cap.isOpened():
                if not self._open():
                    failures += 1
                    if max_failures and failures >= max_failures:
                        logger.error("Exceeded max reconnect attempts for %s", self.camera_id)
                        return
                    logger.info(
                        "Reconnecting %s in %ds (attempt %d)…",
                        self.camera_id,
                        RECONNECT_DELAY,
                        failures,
                    )
                    time.sleep(RECONNECT_DELAY)
                    continue
                failures = 0

            cap = self._cap
            if cap is None:
                continue
            ok, frame = cap.read()
            if not ok:
                logger.warning("Read failure on %s — reconnecting", self.camera_id)
                cap.release()
                self._cap = None
                time.sleep(RECONNECT_DELAY)
                continue

            now = time.monotonic()
            if now - last_yield_time < interval:
                continue  # throttle: skip this frame

            last_yield_time = now
            yield Frame(camera_id=self.camera_id, image=frame, timestamp=time.time())

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
