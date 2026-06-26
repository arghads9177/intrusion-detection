"""Request / response schemas for the FastAPI endpoints.

Kept separate from models.py so request payloads can be typed independently
of what gets persisted in MongoDB.
"""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Zone
# ---------------------------------------------------------------------------


class ZoneUpdate(BaseModel):
    polygon: list[list[float]]
    zone_name: str = "default"


class ZoneResponse(BaseModel):
    camera_id: str
    zone_name: str
    polygon: list[list[float]]


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class RulesUpdate(BaseModel):
    active_hours_start: str = "00:00"
    active_hours_end: str = "23:59"
    sensitivity: float = Field(default=0.4, ge=0.0, le=1.0)
    suppressed_classes: list[str] = Field(default_factory=list)


class RulesResponse(BaseModel):
    camera_id: str
    active_hours_start: str
    active_hours_end: str
    sensitivity: float
    suppressed_classes: list[str]


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------


class CameraResponse(BaseModel):
    id: str
    name: str
    rtsp_url: str
    location_type: str
    enabled: bool


# ---------------------------------------------------------------------------
# Event ingest (from worker)
# ---------------------------------------------------------------------------


class EventIngest(BaseModel):
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


# ---------------------------------------------------------------------------
# Event response
# ---------------------------------------------------------------------------


class EventResponse(BaseModel):
    id: str
    camera_id: str
    timestamp: datetime
    object_class: str
    confidence: float
    bbox: list[float]
    zone_id: str
    track_id: int | None = None
    snapshot_path: str
    clip_path: str
    rule_applied: str
    status: str


class EventsPage(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[EventResponse]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class PerCameraStats(BaseModel):
    camera_id: str
    intrusions: int
    suppressed: int


class StatsResponse(BaseModel):
    total_intrusions: int
    total_suppressed: int
    per_camera: list[PerCameraStats]


# ---------------------------------------------------------------------------
# WebSocket alert payload
# Intentionally identical to EventResponse so the dashboard only needs
# one schema for both REST and WS.
# ---------------------------------------------------------------------------


class AlertPayload(BaseModel):
    id: str
    camera_id: str
    timestamp: datetime
    object_class: str
    confidence: float
    bbox: list[float]
    zone_id: str
    track_id: int | None = None
    snapshot_path: str
    clip_path: str
    rule_applied: str
    status: str
