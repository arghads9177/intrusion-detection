"""Camera, zone, and rules endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.db import get_async_db
from backend.schemas import (
    CameraResponse,
    RulesResponse,
    RulesUpdate,
    ZoneResponse,
    ZoneUpdate,
)

router = APIRouter()


def _db():
    return get_async_db()


# ---------------------------------------------------------------------------
# Cameras
# ---------------------------------------------------------------------------


@router.get("/cameras", response_model=list[CameraResponse], tags=["cameras"])
async def list_cameras(db=Depends(_db)):
    docs = await db.cameras.find({}).to_list(length=None)
    return [
        CameraResponse(
            id=d["cameraId"],
            name=d["name"],
            rtsp_url=d["rtspUrl"],
            location_type=d["locationType"],
            enabled=d.get("enabled", True),
        )
        for d in docs
    ]


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------


@router.get("/cameras/{camera_id}/zone", response_model=ZoneResponse, tags=["cameras"])
async def get_zone(camera_id: str, db=Depends(_db)):
    doc = await db.zones.find_one({"camera_id": camera_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Zone not found for {camera_id}")
    return ZoneResponse(
        camera_id=doc["camera_id"],
        zone_name=doc.get("zone_name", "default"),
        polygon=doc["polygon"],
    )


@router.post("/cameras/{camera_id}/zone", response_model=ZoneResponse, tags=["cameras"])
@router.put("/cameras/{camera_id}/zone", response_model=ZoneResponse, tags=["cameras"])
async def upsert_zone(camera_id: str, body: ZoneUpdate, db=Depends(_db)):
    await db.zones.update_one(
        {"camera_id": camera_id},
        {
            "$set": {
                "camera_id": camera_id,
                "zone_name": body.zone_name,
                "polygon": body.polygon,
            }
        },
        upsert=True,
    )
    return ZoneResponse(
        camera_id=camera_id,
        zone_name=body.zone_name,
        polygon=body.polygon,
    )


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


@router.get("/cameras/{camera_id}/rules", response_model=RulesResponse, tags=["cameras"])
async def get_rules(camera_id: str, db=Depends(_db)):
    doc = await db.rules.find_one({"camera_id": camera_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Rules not found for {camera_id}")
    return RulesResponse(
        camera_id=doc["camera_id"],
        active_hours_start=doc.get("active_hours_start", "00:00"),
        active_hours_end=doc.get("active_hours_end", "23:59"),
        sensitivity=float(doc.get("sensitivity", 0.4)),
        suppressed_classes=doc.get("suppressed_classes", []),
    )


@router.post("/cameras/{camera_id}/rules", response_model=RulesResponse, tags=["cameras"])
@router.put("/cameras/{camera_id}/rules", response_model=RulesResponse, tags=["cameras"])
async def upsert_rules(camera_id: str, body: RulesUpdate, db=Depends(_db)):
    await db.rules.update_one(
        {"camera_id": camera_id},
        {
            "$set": {
                "camera_id": camera_id,
                "active_hours_start": body.active_hours_start,
                "active_hours_end": body.active_hours_end,
                "sensitivity": body.sensitivity,
                "suppressed_classes": body.suppressed_classes,
            }
        },
        upsert=True,
    )
    return RulesResponse(
        camera_id=camera_id,
        active_hours_start=body.active_hours_start,
        active_hours_end=body.active_hours_end,
        sensitivity=body.sensitivity,
        suppressed_classes=body.suppressed_classes,
    )
