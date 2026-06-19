import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "pids_poc")

RTSP_BASE_URL = os.getenv("RTSP_BASE_URL", "rtsp://localhost:8554")

MEDIA_DIR = BASE_DIR / "media"
SNAPSHOTS_DIR = MEDIA_DIR / "snapshots"
CLIPS_DIR = MEDIA_DIR / "clips"

FPS_THROTTLE = int(os.getenv("FPS_THROTTLE", "5"))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.4"))
TORCH_NUM_THREADS = int(os.getenv("TORCH_NUM_THREADS", "4"))

YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")
FRAME_DOWNSCALE_WIDTH = int(os.getenv("FRAME_DOWNSCALE_WIDTH", "640"))

COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "30"))
TEMPORAL_CONFIRM_FRAMES = int(os.getenv("TEMPORAL_CONFIRM_FRAMES", "3"))

CAMERAS_CONFIG = BASE_DIR / "config" / "cameras.yaml"
