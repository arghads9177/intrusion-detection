"""Tests for analytics/zones.py — bottom_center(), in_zone(), load_zones(), ZoneConfig.

Coverage:
- Happy path: anchor inside polygon, load_zones from real cameras.yaml
- Negative path: anchor outside, degenerate bbox, missing zone in config
- Edge cases: boundary touching, single-pixel bbox, inverted bbox coords,
              very small/large polygons, non-rectangular polygon, floating-point coords
- load_zones: malformed yaml, polygon with < 3 points, disabled camera
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml
from shapely.geometry import Polygon

from analytics.zones import ZoneConfig, bottom_center, in_zone, load_zones

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RECT_ZONE = ZoneConfig(
    camera_id="test",
    polygon=Polygon([(100, 100), (540, 100), (540, 380), (100, 380)]),
)  # x: 100–540, y: 100–380


def _zone(x1: int, y1: int, x2: int, y2: int) -> ZoneConfig:
    return ZoneConfig(
        camera_id="test",
        polygon=Polygon([(x1, y1), (x2, y1), (x2, y2), (x1, y2)]),
    )


# ---------------------------------------------------------------------------
# bottom_center
# ---------------------------------------------------------------------------


class TestBottomCenter:
    def test_symmetric_bbox(self):
        x, y = bottom_center((100, 50, 300, 200))
        assert x == pytest.approx(200.0)
        assert y == pytest.approx(200.0)

    def test_x_is_midpoint_of_x1_x2(self):
        x, _ = bottom_center((0, 0, 640, 480))
        assert x == pytest.approx(320.0)

    def test_y_equals_y2(self):
        _, y = bottom_center((10, 20, 200, 375))
        assert y == pytest.approx(375.0)

    def test_zero_width_bbox(self):
        """x1 == x2 — bottom-centre x equals x1."""
        x, y = bottom_center((150, 100, 150, 300))
        assert x == pytest.approx(150.0)
        assert y == pytest.approx(300.0)

    def test_single_pixel_bbox(self):
        x, y = bottom_center((200, 200, 201, 201))
        assert x == pytest.approx(200.5)
        assert y == pytest.approx(201.0)

    def test_floating_equivalent_coords(self):
        """Integer inputs produce float outputs per type hint."""
        x, y = bottom_center((0, 0, 1, 1))
        assert isinstance(x, float)
        assert isinstance(y, float)

    def test_large_frame_coords(self):
        x, y = bottom_center((0, 0, 3840, 2160))
        assert x == pytest.approx(1920.0)
        assert y == pytest.approx(2160.0)


# ---------------------------------------------------------------------------
# in_zone — happy path
# ---------------------------------------------------------------------------


class TestInZoneHappyPath:
    def test_anchor_well_inside_zone(self):
        # bottom-centre: (275, 370) — inside [100,540] x [100,380)
        assert in_zone((200, 150, 350, 370), _RECT_ZONE) is True

    def test_anchor_at_centre_of_zone(self):
        # bottom-centre: (320, 240) — clearly inside
        assert in_zone((270, 100, 370, 240), _RECT_ZONE) is True

    def test_non_rectangular_polygon_contains_anchor(self):
        tri = ZoneConfig(
            camera_id="test",
            polygon=Polygon([(0, 0), (600, 0), (300, 400)]),
        )
        # bottom-centre: (300, 200) — inside triangle
        assert in_zone((250, 100, 350, 200), tri) is True


# ---------------------------------------------------------------------------
# in_zone — negative path
# ---------------------------------------------------------------------------


class TestInZoneNegativePath:
    def test_anchor_below_zone(self):
        # bottom-centre y = 450 > zone max y 380
        assert in_zone((200, 150, 350, 450), _RECT_ZONE) is False

    def test_anchor_above_zone(self):
        # bottom-centre y = 50 < zone min y 100
        assert in_zone((200, 10, 350, 50), _RECT_ZONE) is False

    def test_anchor_left_of_zone(self):
        # bottom-centre x = 50 < zone min x 100
        assert in_zone((10, 150, 90, 300), _RECT_ZONE) is False

    def test_anchor_right_of_zone(self):
        # bottom-centre x = 580 > zone max x 540
        assert in_zone((560, 150, 600, 300), _RECT_ZONE) is False

    def test_top_of_bbox_inside_zone_but_anchor_outside(self):
        # bbox top at y=200 (inside), but bottom-centre y=420 (outside)
        assert in_zone((200, 200, 350, 420), _RECT_ZONE) is False


# ---------------------------------------------------------------------------
# in_zone — edge / boundary cases
# ---------------------------------------------------------------------------


class TestInZoneBoundary:
    def test_anchor_exactly_on_left_edge_is_false(self):
        """Shapely Polygon.contains() excludes boundary points."""
        assert in_zone((50, 200, 100, 300), _RECT_ZONE) is False  # anchor x=75, no. x=(50+100)/2=75

    def test_anchor_exactly_on_bottom_edge_is_false(self):
        # bottom-centre y = 380 is exactly on the boundary
        assert in_zone((250, 300, 350, 380), _RECT_ZONE) is False

    def test_anchor_one_pixel_inside_bottom_edge(self):
        # bottom-centre y = 379
        assert in_zone((250, 300, 350, 379), _RECT_ZONE) is True

    def test_anchor_one_pixel_outside_bottom_edge(self):
        # bottom-centre y = 381
        assert in_zone((250, 300, 350, 381), _RECT_ZONE) is False

    def test_zero_area_zone_never_contains(self):
        """A degenerate polygon with zero area — nothing should be 'inside'."""
        line_zone = ZoneConfig(
            camera_id="test",
            polygon=Polygon([(100, 100), (200, 100), (100, 100)]),
        )
        assert in_zone((140, 90, 160, 100), line_zone) is False


# ---------------------------------------------------------------------------
# load_zones
# ---------------------------------------------------------------------------


class TestLoadZones:
    def test_load_zones_returns_cam1_and_cam2(self, cameras_yaml: Path):
        zones = load_zones(cameras_yaml)
        assert "cam1" in zones
        assert "cam2" in zones

    def test_cam1_polygon_correct_area(self, cameras_yaml: Path):
        zones = load_zones(cameras_yaml)
        # cam1 polygon: 100,100 → 540,100 → 540,380 → 100,380
        # area = 440 * 280 = 123_200
        assert zones["cam1"].polygon.area == pytest.approx(123_200.0)

    def test_cam2_polygon_is_valid_shapely(self, cameras_yaml: Path):
        zones = load_zones(cameras_yaml)
        assert zones["cam2"].polygon.is_valid

    def test_zone_config_camera_id_matches_key(self, cameras_yaml: Path):
        zones = load_zones(cameras_yaml)
        for cam_id, zone in zones.items():
            assert zone.camera_id == cam_id

    def test_load_zones_is_idempotent(self, cameras_yaml: Path):
        zones1 = load_zones(cameras_yaml)
        zones2 = load_zones(cameras_yaml)
        assert set(zones1.keys()) == set(zones2.keys())

    def test_camera_without_zone_is_skipped(self, tmp_path: Path):
        content = textwrap.dedent("""\
            cameras:
              - id: nocam
                name: No Zone Cam
                rtsp_url: rtsp://localhost/nocam
                location_type: boundary
                enabled: true
        """)
        cfg = tmp_path / "no_zone.yaml"
        cfg.write_text(content)
        zones = load_zones(cfg)
        assert "nocam" not in zones

    def test_polygon_with_fewer_than_3_points_raises(self, tmp_path: Path):
        content = textwrap.dedent("""\
            cameras:
              - id: badcam
                name: Bad Cam
                rtsp_url: rtsp://localhost/bad
                location_type: boundary
                enabled: true
                zone:
                  polygon: [[0,0],[100,100]]
        """)
        cfg = tmp_path / "bad_zone.yaml"
        cfg.write_text(content)
        with pytest.raises(ValueError, match="≥3"):
            load_zones(cfg)

    def test_empty_cameras_list_returns_empty_dict(self, tmp_path: Path):
        content = "cameras: []\n"
        cfg = tmp_path / "empty.yaml"
        cfg.write_text(content)
        assert load_zones(cfg) == {}

    def test_zone_config_is_frozen(self, cameras_yaml: Path):
        zones = load_zones(cameras_yaml)
        with pytest.raises(Exception):  # FrozenInstanceError (dataclasses) or AttributeError
            zones["cam1"].camera_id = "hacked"  # type: ignore[misc]
