import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# MongoDB — replica-set connection
# ---------------------------------------------------------------------------
_MONGO_HOSTS = os.getenv("MONGO_HOSTS", "rs1.sisx.in:27001,rs2.sisx.in:27001,rs3.sisx.in:27000")
_MONGO_REPLICA_SET = os.getenv("MONGO_REPLICA_SET", "rssisx")
_MONGO_USER = os.getenv("MONGO_USER", "viadmin")
_MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "vi4eO#Ai")
_MONGO_AUTH_SOURCE = os.getenv("MONGO_AUTH_SOURCE", "videoAnalyticDB")

MONGO_DB_NAME = os.getenv("MONGO_DB", "videoAnalyticDB")

# Build URI only when individual parts are present; allow a full override via MONGO_URI.
_default_uri = (
    f"mongodb://{quote_plus(_MONGO_USER)}:{quote_plus(_MONGO_PASSWORD)}"
    f"@{_MONGO_HOSTS}/{MONGO_DB_NAME}"
    f"?replicaSet={_MONGO_REPLICA_SET}&authSource={_MONGO_AUTH_SOURCE}"
)
MONGO_URI = os.getenv("MONGO_URI", _default_uri)

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

# FastAPI backend base URL used by the worker to POST events
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
