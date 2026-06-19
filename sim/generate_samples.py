"""Generate synthetic sample videos for CCTV simulation testing.

Creates short loopable clips with moving shapes that simulate:
- person_intrusion.mp4: rectangle (person silhouette) walking across frame
- animal_motion.mp4: small circle (animal) moving near ground level
- empty_scene.mp4: static background with slight noise (no threats)
"""

import sys
from pathlib import Path

import cv2
import numpy as np

SAMPLES_DIR = Path(__file__).parent / "samples"
WIDTH, HEIGHT = 640, 480
FPS = 25
DURATION_SEC = 10


def _draw_background(frame: np.ndarray) -> None:
    frame[:HEIGHT // 2] = (180, 130, 80)  # sky (BGR)
    frame[HEIGHT // 2:] = (50, 120, 60)   # ground
    cv2.line(frame, (0, HEIGHT // 2), (WIDTH, HEIGHT // 2), (40, 100, 50), 2)

    noise = np.random.randint(-3, 4, frame.shape, dtype=np.int16)
    np.clip(frame.astype(np.int16) + noise, 0, 255, out=noise)
    frame[:] = noise.astype(np.uint8)


def _create_writer(name: str) -> cv2.VideoWriter:
    path = str(SAMPLES_DIR / name)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    return cv2.VideoWriter(path, fourcc, FPS, (WIDTH, HEIGHT))


def generate_person_intrusion() -> None:
    writer = _create_writer("person_intrusion.mp4")
    total_frames = FPS * DURATION_SEC

    for i in range(total_frames):
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        _draw_background(frame)

        x = int((i / total_frames) * (WIDTH + 80)) - 40
        y_top = HEIGHT // 2 - 100
        y_bottom = HEIGHT // 2 + 60

        cv2.rectangle(frame, (x - 15, y_top), (x + 15, y_top + 25), (0, 180, 255), -1)
        cv2.rectangle(frame, (x - 20, y_top + 25), (x + 20, y_bottom), (0, 0, 200), -1)
        cv2.rectangle(frame, (x - 20, y_bottom), (x - 5, y_bottom + 50), (80, 80, 80), -1)
        cv2.rectangle(frame, (x + 5, y_bottom), (x + 20, y_bottom + 50), (80, 80, 80), -1)

        cv2.putText(frame, "CAM1 - Boundary", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        writer.write(frame)

    writer.release()
    print(f"  Created person_intrusion.mp4 ({total_frames} frames)")


def generate_animal_motion() -> None:
    writer = _create_writer("animal_motion.mp4")
    total_frames = FPS * DURATION_SEC

    for i in range(total_frames):
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        _draw_background(frame)

        t = i / total_frames
        x = int(WIDTH * 0.8 - t * WIDTH * 0.6)
        y = HEIGHT // 2 + 40 + int(10 * np.sin(i * 0.3))

        cv2.ellipse(frame, (x, y), (25, 15), 0, 0, 360, (60, 140, 180), -1)
        cv2.ellipse(frame, (x + 20, y - 5), (10, 8), 0, 0, 360, (60, 140, 180), -1)
        tail_end = (x - 25 + int(5 * np.sin(i * 0.5)), y - 5)
        cv2.line(frame, (x - 20, y - 5), tail_end, (60, 140, 180), 2)

        cv2.putText(frame, "CAM2 - Central Store", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        writer.write(frame)

    writer.release()
    print(f"  Created animal_motion.mp4 ({total_frames} frames)")


def generate_empty_scene() -> None:
    writer = _create_writer("empty_scene.mp4")
    total_frames = FPS * DURATION_SEC

    for i in range(total_frames):
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        _draw_background(frame)

        cv2.putText(frame, "CAM1 - Boundary", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        writer.write(frame)

    writer.release()
    print(f"  Created empty_scene.mp4 ({total_frames} frames)")


def main() -> None:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    existing = [f.name for f in SAMPLES_DIR.glob("*.mp4")]
    if existing and "--force" not in sys.argv:
        print(f"Sample videos already exist: {existing}")
        print("Use --force to regenerate.")
        return

    print("Generating synthetic sample videos...")
    generate_person_intrusion()
    generate_animal_motion()
    generate_empty_scene()
    print("Done. Videos saved to sim/samples/")


if __name__ == "__main__":
    main()
