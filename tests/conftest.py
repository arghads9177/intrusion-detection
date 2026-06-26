"""Shared pytest fixtures for the PIDS test suite.

Fixtures provided:
- cameras_yaml      : Path to the real cameras.yaml config file
- tmp_cameras_yaml  : Path to a temp cameras.yaml written to tmp_path
- fake_frame        : A black 480x640 numpy frame
- person_detection  : A Detection(person) inside the cam1 zone
- dog_detection     : A Detection(dog) inside the cam1 zone
- zone_cam1         : ZoneConfig parsed from cameras.yaml for cam1
- rules_cam1        : CameraRules for cam1 (always active)
- rules_cam2        : CameraRules for cam2 (18:00–08:00 wrap-around)
- tracker           : A fresh TemporalTracker(required_frames=3)
- app               : The FastAPI app with a test async MongoDB database injected
- async_client      : An httpx AsyncClient backed by the FastAPI ASGI app
- mongo_available   : Session-scoped skip guard — skips tests when MongoDB unreachable
- test_db           : Sync MongoDB database handle using db_name="test_videoAnalyticDB"
- async_test_db     : Async Motor database handle for the test database
"""

from __future__ import annotations

import textwrap
from datetime import time
from pathlib import Path

import numpy as np
import pytest
import pytest_asyncio
from shapely.geometry import Polygon

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CAMERAS_YAML = PROJECT_ROOT / "config" / "cameras.yaml"

# ---------------------------------------------------------------------------
# Pure-logic fixtures (no I/O)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def cameras_yaml() -> Path:
    return CAMERAS_YAML


@pytest.fixture
def tmp_cameras_yaml(tmp_path: Path) -> Path:
    """A minimal cameras.yaml written into a pytest tmp_path."""
    content = textwrap.dedent("""\
        cameras:
          - id: cam1
            name: Boundary Camera 1
            rtsp_url: rtsp://localhost:8554/cam1
            location_type: boundary
            enabled: true
            zone:
              polygon: [[100,100],[540,100],[540,380],[100,380]]
            rules:
              active_hours_start: "00:00"
              active_hours_end: "23:59"
              sensitivity: 0.4
              suppressed_classes: [dog, cat, bird, horse, cow, sheep]

          - id: cam2
            name: Central Store Camera
            rtsp_url: rtsp://localhost:8554/cam2
            location_type: central_store
            enabled: true
            zone:
              polygon: [[80,60],[560,60],[560,400],[80,400]]
            rules:
              active_hours_start: "18:00"
              active_hours_end: "08:00"
              sensitivity: 0.4
              suppressed_classes: [dog, cat, bird, horse, cow, sheep]
    """)
    p = tmp_path / "cameras.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def fake_frame() -> np.ndarray:
    """Black 480x640x3 uint8 frame — safe to pass to cv2.imwrite."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def person_detection():
    from analytics.detector import Detection

    return Detection(
        class_name="person",
        confidence=0.88,
        bbox=(200, 150, 350, 370),  # bottom-centre (275, 370) — inside cam1 zone
        track_id=1,
    )


@pytest.fixture
def dog_detection():
    from analytics.detector import Detection

    return Detection(
        class_name="dog",
        confidence=0.75,
        bbox=(200, 150, 350, 370),
        track_id=None,
    )


@pytest.fixture
def zone_cam1():
    from analytics.zones import ZoneConfig

    poly = Polygon([(100, 100), (540, 100), (540, 380), (100, 380)])
    return ZoneConfig(camera_id="cam1", polygon=poly)


@pytest.fixture
def rules_cam1():
    from analytics.rules import CameraRules

    return CameraRules(
        camera_id="cam1",
        active_hours_start=time(0, 0),
        active_hours_end=time(23, 59),
        sensitivity=0.4,
        suppressed_classes=frozenset(["dog", "cat", "bird", "horse", "cow", "sheep"]),
    )


@pytest.fixture
def rules_cam2():
    from analytics.rules import CameraRules

    return CameraRules(
        camera_id="cam2",
        active_hours_start=time(18, 0),
        active_hours_end=time(8, 0),
        sensitivity=0.4,
        suppressed_classes=frozenset(["dog", "cat", "bird", "horse", "cow", "sheep"]),
    )


@pytest.fixture
def tracker():
    from analytics.worker import TemporalTracker

    return TemporalTracker(required_frames=3)


# ---------------------------------------------------------------------------
# MongoDB fixtures
# ---------------------------------------------------------------------------

_TEST_DB_NAME = "test_videoAnalyticDB"
_TEST_CAM = "test_cam"


@pytest.fixture(scope="session")
def mongo_available():
    """Skip tests if MongoDB replica-set is unreachable."""
    from pymongo import MongoClient

    from config.settings import MONGO_URI

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
    except Exception as exc:
        pytest.skip(f"MongoDB not reachable — skipping: {exc}")


@pytest.fixture
def test_db(mongo_available):
    """Synchronous PyMongo handle for the test database; cleans up test_cam docs."""
    from backend.db import get_sync_db

    db = get_sync_db(_TEST_DB_NAME)
    # pre-clean
    db.events.delete_many({"camera_id": _TEST_CAM})
    db.suppressed_detections.delete_many({"camera_id": _TEST_CAM})
    yield db
    # post-clean
    db.events.delete_many({"camera_id": _TEST_CAM})
    db.suppressed_detections.delete_many({"camera_id": _TEST_CAM})


@pytest_asyncio.fixture
async def async_test_db(mongo_available):
    """Async Motor handle for the test database; cleans up test_cam docs."""
    from backend.db import get_async_db

    db = get_async_db(_TEST_DB_NAME)
    await db.events.delete_many({"camera_id": _TEST_CAM})
    await db.suppressed_detections.delete_many({"camera_id": _TEST_CAM})
    yield db
    await db.events.delete_many({"camera_id": _TEST_CAM})
    await db.suppressed_detections.delete_many({"camera_id": _TEST_CAM})


# ---------------------------------------------------------------------------
# FastAPI test client fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_client(async_test_db):
    """httpx AsyncClient backed by the FastAPI ASGI app with test DB injected."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.routes.cameras import _db as cameras_db
    from backend.routes.events import _db as events_db
    from backend.routes.stats import _db as stats_db

    def _override_db():
        return async_test_db

    app.dependency_overrides[cameras_db] = _override_db
    app.dependency_overrides[events_db] = _override_db
    app.dependency_overrides[stats_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()
