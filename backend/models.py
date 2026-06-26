"""Pydantic v2 models that mirror the MongoDB document schema.

These are used for serialisation/deserialisation between Motor and FastAPI.
`_id` is mapped to `id` (str) via alias so the API never exposes BSON ObjectIds.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CameraModel(BaseModel):
    id: str = Field(alias="cameraId")
    name: str
    rtsp_url: str = Field(alias="rtspUrl")
    location_type: str = Field(alias="locationType")
    enabled: bool = True

    model_config = {"populate_by_name": True}


class ZoneModel(BaseModel):
    camera_id: str
    zone_name: str = "default"
    # List of [x, y] pairs
    polygon: list[list[float]]

    model_config = {"populate_by_name": True}


class RulesModel(BaseModel):
    camera_id: str
    active_hours_start: str = "00:00"
    active_hours_end: str = "23:59"
    sensitivity: float = 0.4
    suppressed_classes: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class EventModel(BaseModel):
    id: str | None = None
    camera_id: str
    timestamp: datetime
    object_class: str
    confidence: float
    bbox: list[float]
    zone_id: str
    track_id: int | None = None
    snapshot_path: str
    clip_path: str
    rule_applied: str = ""
    status: str = "raised"
    cooldown_until: datetime | None = None

    model_config = {"populate_by_name": True}


def _doc_to_event(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw Mongo event doc to a dict suitable for EventModel."""
    out = dict(doc)
    raw_id = out.pop("_id", None)
    if raw_id is not None:
        out["id"] = str(raw_id)
    return out
