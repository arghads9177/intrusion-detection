"""Verify RTSP streams are accessible by grabbing a frame from each camera."""

import sys

import cv2


def verify(url: str) -> bool:
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        print(f"  FAIL: cannot open {url}")
        return False

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print(f"  FAIL: opened {url} but could not read a frame")
        return False

    h, w = frame.shape[:2]
    print(f"  OK:   {url}  ({w}x{h})")
    return True


def main() -> None:
    urls = sys.argv[1:] or [
        "rtsp://localhost:8554/cam1",
        "rtsp://localhost:8554/cam2",
    ]

    print("Verifying RTSP streams...")
    results = [verify(url) for url in urls]

    if all(results):
        print("All streams OK.")
    else:
        print("Some streams FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
