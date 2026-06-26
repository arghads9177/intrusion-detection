"""Integration tests for Phase 4: event storage, cooldown, and DB persistence.

Uses the configured videoAnalyticDB. Test documents are scoped to
camera_id = "test_cam" and are deleted before / after each test so production
data is never touched.

Run with:  pytest tests/test_phase4_integration.py -v
"""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from pymongo import MongoClient

from analytics.detector import Detection
from analytics.events import EventManager
from backend.db import (
    ensure_indexes,
    find_events,
    get_sync_db,
    insert_event,
    insert_suppressed,
    seed_from_config,
)
from config.settings import MONGO_DB_NAME, MONGO_URI

_CAM = "test_cam"
_ZONE = "test_cam_zone"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def mongo_available():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
    except Exception as exc:
        pytest.skip(f"MongoDB not reachable — skipping integration tests: {exc}")


def _purge_test_data():
    db = get_sync_db()
    db.events.delete_many({"camera_id": _CAM})
    db.suppressed_detections.delete_many({"camera_id": _CAM})


@pytest.fixture(autouse=True)
def clean_test_data(mongo_available):
    """Delete test_cam documents before and after each test."""
    _purge_test_data()
    yield
    _purge_test_data()


@pytest.fixture
def fake_frame() -> np.ndarray:
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def person_detection() -> Detection:
    return Detection(
        class_name="person",
        confidence=0.88,
        bbox=(200, 150, 350, 380),
        track_id=1,
    )


@pytest.fixture
def dog_detection() -> Detection:
    return Detection(
        class_name="dog",
        confidence=0.75,
        bbox=(100, 100, 250, 300),
        track_id=None,
    )


@pytest.fixture
def event_manager(tmp_path):
    """EventManager wired to the production DB with temp media directories."""
    import config.settings as settings

    original_snap = settings.SNAPSHOTS_DIR
    original_clips = settings.CLIPS_DIR
    settings.SNAPSHOTS_DIR = tmp_path / "snapshots"
    settings.CLIPS_DIR = tmp_path / "clips"

    mgr = EventManager(camera_id=_CAM, fps=5.0)
    yield mgr
    mgr.close()

    settings.SNAPSHOTS_DIR = original_snap
    settings.CLIPS_DIR = original_clips


# ---------------------------------------------------------------------------
# DB layer tests
# ---------------------------------------------------------------------------


class TestDbLayer:
    def test_insert_and_find_event(self, mongo_available):
        ensure_indexes()
        doc = {
            "camera_id": _CAM,
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
            "object_class": "person",
            "confidence": 0.9,
            "bbox": [10, 20, 100, 200],
            "zone_id": _ZONE,
            "snapshot_path": "test/snap.jpg",
            "clip_path": "test/clip.mp4",
            "status": "raised",
        }
        eid = insert_event(doc)
        assert len(eid) > 0

        events = find_events(camera_id=_CAM)
        assert len(events) == 1
        assert events[0]["object_class"] == "person"

    def test_insert_suppressed(self, mongo_available):
        doc = {
            "camera_id": _CAM,
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
            "object_class": "dog",
            "confidence": 0.72,
            "bbox": [5, 5, 50, 50],
            "reason": "animal",
        }
        sid = insert_suppressed(doc)
        assert len(sid) > 0
        db = get_sync_db()
        assert db.suppressed_detections.count_documents({"camera_id": _CAM}) == 1

    def test_seed_from_config(self, mongo_available):
        seed_from_config()
        db = get_sync_db()
        assert db.cameras.find_one({"cameraId": "cam1"}) is not None
        assert db.cameras.find_one({"cameraId": "cam2"}) is not None
        assert db.zones.find_one({"_id": "cam1_zone"}) is not None
        assert db.rules.find_one({"_id": "cam1_rules"}) is not None

    def test_seed_is_idempotent(self, mongo_available):
        seed_from_config()
        seed_from_config()
        db = get_sync_db()
        # Upsert must not create duplicates — count for exactly our two cameras
        assert db.cameras.count_documents({"cameraId": {"$in": ["cam1", "cam2"]}}) == 2


# ---------------------------------------------------------------------------
# EventManager tests
# ---------------------------------------------------------------------------


class TestEventManager:
    def test_confirmed_event_writes_db_record(
        self, event_manager, fake_frame, person_detection, mongo_available
    ):
        event_manager.feed_frame(fake_frame)
        fired = event_manager.on_confirmed(person_detection, _ZONE, fake_frame)

        assert fired is True
        events = find_events(camera_id=_CAM)
        assert len(events) == 1
        doc = events[0]
        assert doc["camera_id"] == _CAM
        assert doc["object_class"] == "person"
        assert doc["status"] == "raised"
        assert doc["zone_id"] == _ZONE

    def test_confirmed_event_saves_snapshot(
        self, event_manager, fake_frame, person_detection, mongo_available
    ):
        import config.settings as settings

        event_manager.feed_frame(fake_frame)
        event_manager.on_confirmed(person_detection, _ZONE, fake_frame)

        events = find_events(camera_id=_CAM)
        snap_rel = events[0]["snapshot_path"]
        snap_abs = Path(settings.SNAPSHOTS_DIR) / snap_rel
        assert snap_abs.exists(), f"Snapshot not found: {snap_abs}"

    def test_confirmed_event_starts_clip(
        self, event_manager, fake_frame, person_detection, mongo_available
    ):
        import config.settings as settings
        from analytics.events import _POST_FRAMES

        for _ in range(10):
            event_manager.feed_frame(fake_frame)

        event_manager.on_confirmed(person_detection, _ZONE, fake_frame)

        for _ in range(_POST_FRAMES + 1):
            event_manager.feed_frame(fake_frame)

        events = find_events(camera_id=_CAM)
        clip_rel = events[0]["clip_path"]
        clip_abs = Path(settings.CLIPS_DIR) / clip_rel
        assert clip_abs.exists(), f"Clip not found: {clip_abs}"

    def test_cooldown_prevents_duplicate_event(
        self, event_manager, fake_frame, person_detection, mongo_available
    ):
        event_manager.feed_frame(fake_frame)
        fired1 = event_manager.on_confirmed(person_detection, _ZONE, fake_frame)
        fired2 = event_manager.on_confirmed(person_detection, _ZONE, fake_frame)
        fired3 = event_manager.on_confirmed(person_detection, _ZONE, fake_frame)

        assert fired1 is True
        assert fired2 is False
        assert fired3 is False

        events = find_events(camera_id=_CAM)
        assert len(events) == 1, "Cooldown should prevent duplicate events"

    def test_suppressed_detection_writes_db_record(
        self, event_manager, dog_detection, mongo_available
    ):
        event_manager.on_suppressed(dog_detection, "animal")

        db = get_sync_db()
        docs = list(db.suppressed_detections.find({"camera_id": _CAM}))
        assert len(docs) == 1
        assert docs[0]["reason"] == "animal"
        assert docs[0]["object_class"] == "dog"

    def test_suppressed_cooldown_avoids_spam(
        self, event_manager, dog_detection, mongo_available
    ):
        for _ in range(5):
            event_manager.on_suppressed(dog_detection, "animal")

        db = get_sync_db()
        assert db.suppressed_detections.count_documents({"camera_id": _CAM}) == 1

    def test_suppressed_goes_to_suppressed_not_events(
        self, event_manager, dog_detection, mongo_available
    ):
        event_manager.on_suppressed(dog_detection, "animal")

        db = get_sync_db()
        assert db.events.count_documents({"camera_id": _CAM}) == 0
        assert db.suppressed_detections.count_documents({"camera_id": _CAM}) == 1

    def test_different_track_ids_fire_independent_events(
        self, event_manager, fake_frame, mongo_available
    ):
        det1 = Detection("person", 0.85, (100, 100, 200, 300), track_id=1)
        det2 = Detection("person", 0.80, (300, 100, 400, 300), track_id=2)

        event_manager.feed_frame(fake_frame)
        event_manager.on_confirmed(det1, _ZONE, fake_frame)
        event_manager.on_confirmed(det2, _ZONE, fake_frame)

        events = find_events(camera_id=_CAM)
        assert len(events) == 2

    def test_event_record_contains_required_fields(
        self, event_manager, fake_frame, person_detection, mongo_available
    ):
        event_manager.feed_frame(fake_frame)
        event_manager.on_confirmed(person_detection, _ZONE, fake_frame)

        events = find_events(camera_id=_CAM)
        doc = events[0]
        required = {
            "camera_id", "timestamp", "object_class", "confidence",
            "bbox", "zone_id", "snapshot_path", "clip_path",
            "rule_applied", "status", "cooldown_until",
        }
        missing = required - set(doc.keys())
        assert not missing, f"Missing fields in event doc: {missing}"

    def test_seeded_collections_contain_cam1_and_cam2(
        self, event_manager, mongo_available
    ):
        # EventManager.__init__ calls seed_from_config
        db = get_sync_db()
        assert db.cameras.find_one({"cameraId": "cam1"}) is not None
        assert db.cameras.find_one({"cameraId": "cam2"}) is not None
        assert db.zones.find_one({"_id": "cam1_zone"}) is not None
        assert db.rules.find_one({"_id": "cam2_rules"}) is not None
