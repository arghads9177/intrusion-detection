"""Stats aggregation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.db import get_async_db
from backend.schemas import PerCameraStats, StatsResponse

router = APIRouter()


def _db():
    return get_async_db()


@router.get("/stats", response_model=StatsResponse, tags=["stats"])
async def get_stats(db=Depends(_db)):
    # Intrusions per camera
    event_pipeline = [
        {"$group": {"_id": "$camera_id", "count": {"$sum": 1}}},
    ]
    suppressed_pipeline = [
        {"$group": {"_id": "$camera_id", "count": {"$sum": 1}}},
    ]

    event_docs = await db.events.aggregate(event_pipeline).to_list(length=None)
    supp_docs = await db.suppressed_detections.aggregate(suppressed_pipeline).to_list(length=None)

    event_by_cam: dict[str, int] = {d["_id"]: d["count"] for d in event_docs}
    supp_by_cam: dict[str, int] = {d["_id"]: d["count"] for d in supp_docs}

    all_cameras = set(event_by_cam) | set(supp_by_cam)
    per_camera = [
        PerCameraStats(
            camera_id=cam,
            intrusions=event_by_cam.get(cam, 0),
            suppressed=supp_by_cam.get(cam, 0),
        )
        for cam in sorted(all_cameras)
    ]

    return StatsResponse(
        total_intrusions=sum(event_by_cam.values()),
        total_suppressed=sum(supp_by_cam.values()),
        per_camera=per_camera,
    )
