"""Unit tests for Phase 3: classifier, zones, rules, temporal confirmation.

Run with:  pytest tests/test_phase3.py -v
"""

from datetime import datetime, time

import pytest
from shapely.geometry import Polygon

from analytics.classifier import ThreatLevel, classify, is_alert_eligible
from analytics.detector import Detection
from analytics.rules import CameraRules, evaluate, is_active_hour
from analytics.worker import (
    DecisionResult,
    TemporalTracker,
    process_frame,
)
from analytics.zones import ZoneConfig, bottom_center, in_zone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rules(
    start: str = "00:00",
    end: str = "23:59",
    suppressed: list[str] | None = None,
) -> CameraRules:
    def t(s: str) -> time:
        h, m = s.split(":")
        return time(int(h), int(m))

    return CameraRules(
        camera_id="test_cam",
        active_hours_start=t(start),
        active_hours_end=t(end),
        sensitivity=0.4,
        suppressed_classes=frozenset(suppressed or []),
    )


def _make_zone(
    x1: int = 100, y1: int = 100, x2: int = 500, y2: int = 400
) -> ZoneConfig:
    poly = Polygon([(x1, y1), (x2, y1), (x2, y2), (x1, y2)])
    return ZoneConfig(camera_id="test_cam", polygon=poly)


def _det(
    class_name: str = "person",
    conf: float = 0.85,
    bbox: tuple[int, int, int, int] = (200, 150, 350, 350),
    track_id: int | None = 1,
) -> Detection:
    return Detection(
        class_name=class_name,
        confidence=conf,
        bbox=bbox,
        track_id=track_id,
    )


# ---------------------------------------------------------------------------
# Classifier tests
# ---------------------------------------------------------------------------

class TestClassifier:
    def test_person_is_threat(self):
        assert classify("person") == ThreatLevel.THREAT

    @pytest.mark.parametrize("cls", ["dog", "cat", "bird", "horse", "cow", "sheep"])
    def test_animals_are_non_threat(self, cls: str):
        assert classify(cls) == ThreatLevel.NON_THREAT

    def test_vehicle_is_ignore(self):
        assert classify("car") == ThreatLevel.IGNORE

    def test_is_alert_eligible_person(self):
        assert is_alert_eligible("person") is True

    def test_is_alert_eligible_dog(self):
        assert is_alert_eligible("dog") is False


# ---------------------------------------------------------------------------
# Zone tests
# ---------------------------------------------------------------------------

class TestZones:
    # zone: x 100–500, y 100–400

    def test_bottom_center_inside(self):
        # bbox entirely inside zone → bottom-centre inside
        zone = _make_zone()
        assert in_zone((200, 150, 350, 380), zone) is True

    def test_bottom_center_outside(self):
        # bbox whose bottom-centre is below the zone polygon
        zone = _make_zone()
        assert in_zone((200, 150, 350, 450), zone) is False

    def test_top_of_bbox_in_zone_but_anchor_outside(self):
        # top of bbox is inside zone but bottom-centre drops below y=400
        zone = _make_zone()
        # bottom-centre y = 410 → outside
        assert in_zone((200, 300, 350, 410), zone) is False

    def test_anchor_exactly_at_boundary(self):
        zone = _make_zone()
        # bottom-centre at (300, 400) — on the edge, Shapely contains() is False
        assert in_zone((250, 350, 350, 400), zone) is False

    def test_bottom_center_calculation(self):
        bx, by = bottom_center((100, 50, 300, 200))
        assert bx == pytest.approx(200.0)
        assert by == pytest.approx(200.0)

    def test_person_outside_polygon(self):
        zone = _make_zone()
        # bbox entirely left of zone (x2 < x1_zone)
        assert in_zone((10, 150, 90, 380), zone) is False


# ---------------------------------------------------------------------------
# Rules tests
# ---------------------------------------------------------------------------

class TestRules:
    def test_normal_window_inside(self):
        rules = _make_rules("09:00", "17:00")
        now = datetime.now().replace(hour=13, minute=0)
        assert is_active_hour(rules, now) is True

    def test_normal_window_outside(self):
        rules = _make_rules("09:00", "17:00")
        now = datetime.now().replace(hour=20, minute=0)
        assert is_active_hour(rules, now) is False

    def test_wraparound_window_after_start(self):
        # 18:00–08:00 → 20:00 is active
        rules = _make_rules("18:00", "08:00")
        now = datetime.now().replace(hour=20, minute=0)
        assert is_active_hour(rules, now) is True

    def test_wraparound_window_before_end(self):
        # 18:00–08:00 → 06:00 is active
        rules = _make_rules("18:00", "08:00")
        now = datetime.now().replace(hour=6, minute=0)
        assert is_active_hour(rules, now) is True

    def test_wraparound_window_inactive_midday(self):
        # 18:00–08:00 → 12:00 is NOT active
        rules = _make_rules("18:00", "08:00")
        now = datetime.now().replace(hour=12, minute=0)
        assert is_active_hour(rules, now) is False

    def test_always_on_camera(self):
        rules = _make_rules("00:00", "23:59")
        for hour in (0, 6, 12, 18, 23):
            now = datetime.now().replace(hour=hour, minute=0)
            assert is_active_hour(rules, now) is True

    def test_suppressed_class_returns_animal(self):
        rules = _make_rules(suppressed=["dog", "cat"])
        assert evaluate("dog", rules) == "animal"
        assert evaluate("cat", rules) == "animal"

    def test_non_suppressed_class_out_of_hours(self):
        rules = _make_rules("18:00", "08:00")
        # midday is out-of-hours for this camera
        now = datetime.now().replace(hour=12, minute=0)
        assert evaluate("person", rules, now) == "out_of_hours"

    def test_non_suppressed_class_in_hours_returns_empty(self):
        rules = _make_rules("18:00", "08:00")
        now = datetime.now().replace(hour=20, minute=0)
        assert evaluate("person", rules, now) == ""


# ---------------------------------------------------------------------------
# Temporal confirmation tests
# ---------------------------------------------------------------------------

class TestTemporalTracker:
    def test_single_frame_no_confirmation(self):
        t = TemporalTracker(required_frames=3)
        t.update("p1", True)
        assert t.is_confirmed("p1") is False

    def test_three_frames_confirms(self):
        t = TemporalTracker(required_frames=3)
        for _ in range(3):
            t.update("p1", True)
        assert t.is_confirmed("p1") is True

    def test_flicker_resets_count(self):
        t = TemporalTracker(required_frames=3)
        t.update("p1", True)
        t.update("p1", True)
        t.update("p1", False)  # flicker
        t.update("p1", True)
        assert t.is_confirmed("p1") is False

    def test_absent_key_resets_via_end_frame(self):
        t = TemporalTracker(required_frames=3)
        t.update("p1", True)
        t.update("p1", True)
        t.end_frame(active_keys=set())  # p1 absent
        t.update("p1", True)
        assert t.is_confirmed("p1") is False  # count restarted from 1


# ---------------------------------------------------------------------------
# Full pipeline process_frame tests
# ---------------------------------------------------------------------------

class TestProcessFrame:
    def _make_tracker(self) -> TemporalTracker:
        return TemporalTracker(required_frames=3)

    def test_in_zone_person_confirmed_after_n_frames(self):
        zone = _make_zone()
        rules = _make_rules()
        tracker = self._make_tracker()
        det = _det("person", bbox=(200, 150, 350, 350))

        # Frames 1 and 2 → PENDING
        for _ in range(2):
            results = process_frame([det], zone, rules, tracker)
            assert len(results) == 1
            assert results[0].status == DecisionResult.PENDING

        # Frame 3 → CONFIRMED
        results = process_frame([det], zone, rules, tracker)
        assert results[0].status == DecisionResult.CONFIRMED

    def test_animal_suppressed_immediately(self):
        zone = _make_zone()
        rules = _make_rules(suppressed=["dog"])
        tracker = self._make_tracker()
        det = _det("dog", bbox=(200, 150, 350, 350))

        results = process_frame([det], zone, rules, tracker)
        assert len(results) == 1
        assert results[0].status == DecisionResult.SUPPRESSED
        assert results[0].reason == "animal"

    def test_person_outside_zone_suppressed(self):
        zone = _make_zone()
        rules = _make_rules()
        tracker = self._make_tracker()
        # bbox bottom-centre is outside zone (x outside 100-500)
        det = _det("person", bbox=(10, 150, 90, 380))

        results = process_frame([det], zone, rules, tracker)
        assert results[0].status == DecisionResult.SUPPRESSED
        assert results[0].reason == "out_of_zone"

    def test_person_out_of_hours_suppressed(self):
        zone = _make_zone()
        rules = _make_rules("18:00", "08:00")  # cam2 style
        tracker = self._make_tracker()
        det = _det("person", bbox=(200, 150, 350, 350))
        midday = datetime.now().replace(hour=12, minute=0)

        results = process_frame([det], zone, rules, tracker, fake_now=midday)
        assert results[0].status == DecisionResult.SUPPRESSED
        assert results[0].reason == "out_of_hours"

    def test_person_after_hours_can_confirm(self):
        zone = _make_zone()
        rules = _make_rules("18:00", "08:00")
        tracker = self._make_tracker()
        det = _det("person", bbox=(200, 150, 350, 350))
        evening = datetime.now().replace(hour=20, minute=0)

        for _ in range(3):
            results = process_frame([det], zone, rules, tracker, fake_now=evening)
        assert results[0].status == DecisionResult.CONFIRMED

    def test_single_frame_flicker_no_confirmation(self):
        zone = _make_zone()
        rules = _make_rules()
        tracker = self._make_tracker()
        det = _det("person", bbox=(200, 150, 350, 350))

        # One frame only
        results = process_frame([det], zone, rules, tracker)
        assert results[0].status == DecisionResult.PENDING
        assert results[0].consecutive == 1

    def test_vehicle_ignored(self):
        zone = _make_zone()
        rules = _make_rules()
        tracker = self._make_tracker()
        det = _det("car", bbox=(200, 150, 350, 350))

        results = process_frame([det], zone, rules, tracker)
        assert len(results) == 0

    def test_no_zone_treats_all_positions_as_in_zone(self):
        rules = _make_rules()
        tracker = self._make_tracker()
        # bbox far outside any zone — but zone=None means zone check skipped
        det = _det("person", bbox=(10, 10, 50, 50))

        for _ in range(3):
            results = process_frame([det], None, rules, tracker)
        assert results[0].status == DecisionResult.CONFIRMED

    def test_cam2_person_during_workhours_suppressed(self):
        """cam2 scenario: central store, alerts only 18:00–08:00."""
        zone = _make_zone(80, 60, 560, 400)
        rules = _make_rules("18:00", "08:00")
        tracker = self._make_tracker()
        det = _det("person", bbox=(200, 150, 450, 380))
        workhour = datetime.now().replace(hour=14, minute=0)

        results = process_frame([det], zone, rules, tracker, fake_now=workhour)
        assert results[0].status == DecisionResult.SUPPRESSED
        assert results[0].reason == "out_of_hours"

    def test_cam2_person_after_hours_confirmed(self):
        zone = _make_zone(80, 60, 560, 400)
        rules = _make_rules("18:00", "08:00")
        tracker = self._make_tracker()
        det = _det("person", bbox=(200, 150, 450, 370))
        after_hours = datetime.now().replace(hour=21, minute=0)

        for _ in range(3):
            results = process_frame([det], zone, rules, tracker, fake_now=after_hours)
        assert results[0].status == DecisionResult.CONFIRMED
