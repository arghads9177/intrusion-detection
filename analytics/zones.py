"""Zone management: load polygon definitions and test detections against them.

Coordinate space: pixel coords on the *downscale-corrected* (original) frame,
i.e. the same space used by Detection.bbox from detector.py.

Anchor point: bbox bottom-centre  (midpoint of the bottom edge) per spec §5.5.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from shapely.geometry import Point, Polygon

from config.settings import CAMERAS_CONFIG

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ZoneConfig:
    camera_id: str
    polygon: Polygon


def _parse_polygon(raw: list[list[int | float]]) -> Polygon:
    coords = [(pt[0], pt[1]) for pt in raw]
    if len(coords) < 3:
        raise ValueError(f"Zone polygon needs ≥3 points, got {len(coords)}")
    return Polygon(coords)


def load_zones(config_path: Path = CAMERAS_CONFIG) -> dict[str, ZoneConfig]:
    """Return a mapping of camera_id → ZoneConfig loaded from cameras.yaml."""
    with open(config_path) as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    zones: dict[str, ZoneConfig] = {}
    for cam in raw.get("cameras", []):
        cam_id: str = cam["id"]
        polygon_raw = cam.get("zone", {}).get("polygon")
        if not polygon_raw:
            logger.warning("No zone polygon defined for %s — skipping", cam_id)
            continue
        poly = _parse_polygon(polygon_raw)
        if not poly.is_valid:
            logger.warning("Zone polygon for %s is not valid — skipping", cam_id)
            continue
        zones[cam_id] = ZoneConfig(camera_id=cam_id, polygon=poly)
        logger.debug(
            "Loaded zone for %s: %d vertices, area=%.0f",
            cam_id,
            len(poly.exterior.coords) - 1,
            poly.area,
        )
    return zones


def bottom_center(bbox: tuple[int, int, int, int]) -> tuple[float, float]:
    """Return the bottom-centre anchor (x, y) of an (x1,y1,x2,y2) bbox."""
    x1, _, x2, y2 = bbox
    return ((x1 + x2) / 2.0, float(y2))


def in_zone(bbox: tuple[int, int, int, int], zone: ZoneConfig) -> bool:
    """Return True if the bbox's bottom-centre falls inside the zone polygon."""
    anchor = bottom_center(bbox)
    return zone.polygon.contains(Point(anchor))
