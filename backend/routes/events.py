"""Events endpoints: list/filter/paginate, ingest, and media serving."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from backend.db import get_async_db
from backend.schemas import AlertPayload, EventIngest, EventResponse, EventsPage
from backend.ws_manager import manager
from config.settings import CLIPS_DIR, SNAPSHOTS_DIR

logger = logging.getLogger(__name__)
router = APIRouter()


def _db():
    return get_async_db()


def _to_response(doc: dict[str, Any]) -> EventResponse:
    return EventResponse(
        id=str(doc["_id"]),
        camera_id=doc["camera_id"],
        timestamp=doc["timestamp"],
        object_class=doc["object_class"],
        confidence=doc["confidence"],
        bbox=doc["bbox"],
        zone_id=doc["zone_id"],
        track_id=doc.get("track_id"),
        snapshot_path=doc["snapshot_path"],
        clip_path=doc["clip_path"],
        rule_applied=doc.get("rule_applied", ""),
        status=doc.get("status", "raised"),
    )


# ---------------------------------------------------------------------------
# List / filter
# ---------------------------------------------------------------------------


@router.get("/events", response_model=EventsPage, tags=["events"])
async def list_events(
    camera_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    object_class: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db=Depends(_db),
):
    query: dict[str, Any] = {}
    if camera_id:
        query["camera_id"] = camera_id
    if since:
        query["timestamp"] = {"$gte": since}
    if object_class:
        query["object_class"] = object_class

    total = await db.events.count_documents(query)
    cursor = db.events.find(query).sort("timestamp", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    return EventsPage(
        total=total,
        skip=skip,
        limit=limit,
        items=[_to_response(d) for d in docs],
    )


# ---------------------------------------------------------------------------
# Ingest (called by worker)
# ---------------------------------------------------------------------------


@router.post("/events", response_model=EventResponse, status_code=201, tags=["events"])
async def ingest_event(body: EventIngest, db=Depends(_db)):
    doc: dict[str, Any] = body.model_dump()
    result = await db.events.insert_one(doc)
    doc["_id"] = result.inserted_id

    event_resp = _to_response(doc)

    # Broadcast to all WS subscribers
    alert = AlertPayload(**event_resp.model_dump())
    await manager.broadcast(alert.model_dump_json())

    logger.info(
        "Event ingested via API  id=%s  camera=%s  class=%s",
        event_resp.id,
        event_resp.camera_id,
        event_resp.object_class,
    )
    return event_resp


# ---------------------------------------------------------------------------
# Media serving
# ---------------------------------------------------------------------------


@router.get("/events/{event_id}/snapshot", tags=["events"])
async def get_snapshot(event_id: str, db=Depends(_db)):
    try:
        oid = ObjectId(event_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event id")

    doc = await db.events.find_one({"_id": oid}, {"snapshot_path": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Event not found")

    path = Path(SNAPSHOTS_DIR) / doc["snapshot_path"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot file not found")
    return FileResponse(str(path), media_type="image/jpeg")


@router.get("/events/{event_id}/clip", tags=["events"])
async def get_clip(event_id: str, db=Depends(_db)):
    try:
        oid = ObjectId(event_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid event id")

    doc = await db.events.find_one({"_id": oid}, {"clip_path": 1})
    if doc is None:
        raise HTTPException(status_code=404, detail="Event not found")

    path = Path(CLIPS_DIR) / doc["clip_path"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Clip file not found")
    return FileResponse(str(path), media_type="video/mp4")
