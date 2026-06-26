"""Per-camera rule evaluation: active hours and suppressed-class checks.

cam1 (boundary): active 00:00–23:59 → always alert
cam2 (central_store): active 18:00–08:00 → alert only outside working hours

'active_hours_start' / 'active_hours_end' are stored in cameras.yaml.
When start > end (e.g. 18:00–08:00) the window wraps midnight.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any

import yaml

from config.settings import CAMERAS_CONFIG

logger = logging.getLogger(__name__)

SuppressedReason = str  # 'animal' | 'out_of_hours' | 'out_of_zone' | ''


@dataclass(frozen=True)
class CameraRules:
    camera_id: str
    active_hours_start: time
    active_hours_end: time
    sensitivity: float
    suppressed_classes: frozenset[str]


def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def load_rules(config_path: Path = CAMERAS_CONFIG) -> dict[str, CameraRules]:
    """Return mapping of camera_id → CameraRules from cameras.yaml."""
    with open(config_path) as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    rules: dict[str, CameraRules] = {}
    for cam in raw.get("cameras", []):
        cam_id: str = cam["id"]
        r = cam.get("rules", {})
        rules[cam_id] = CameraRules(
            camera_id=cam_id,
            active_hours_start=_parse_time(r.get("active_hours_start", "00:00")),
            active_hours_end=_parse_time(r.get("active_hours_end", "23:59")),
            sensitivity=float(r.get("sensitivity", 0.4)),
            suppressed_classes=frozenset(r.get("suppressed_classes", [])),
        )
        logger.debug(
            "Rules for %s: active %s–%s, suppressed=%s",
            cam_id,
            rules[cam_id].active_hours_start,
            rules[cam_id].active_hours_end,
            rules[cam_id].suppressed_classes,
        )
    return rules


def is_active_hour(rules: CameraRules, now: datetime | None = None) -> bool:
    """Return True if *now* falls inside the camera's active hours window.

    Handles wrap-around windows (e.g. 18:00–08:00 spans midnight).
    """
    t = (now or datetime.now()).time().replace(second=0, microsecond=0)
    start = rules.active_hours_start
    end = rules.active_hours_end

    if start <= end:
        # Normal window: e.g. 09:00–17:00
        return start <= t <= end
    else:
        # Wrap-around: e.g. 18:00–08:00 means 18:00..23:59 OR 00:00..08:00
        return t >= start or t <= end


def evaluate(
    class_name: str,
    rules: CameraRules,
    now: datetime | None = None,
) -> SuppressedReason:
    """Return a suppression reason string, or '' if the detection should proceed.

    Checks (in order):
    1. Class is in suppressed_classes → 'animal'
    2. Current time is outside active window → 'out_of_hours'
    3. Nothing → ''  (caller still needs to check zone + temporal confirm)
    """
    if class_name in rules.suppressed_classes:
        return "animal"
    if not is_active_hour(rules, now):
        return "out_of_hours"
    return ""
