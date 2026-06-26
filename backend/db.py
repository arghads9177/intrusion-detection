"""MongoDB connection and CRUD layer shared between the worker and the API.

Sync client (PyMongo) is used by the analytics worker.
Async client (Motor) is exposed for the FastAPI backend (Phase 5).
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pymongo
import yaml
from pymongo import MongoClient
from pymongo.database import Database

import motor.motor_asyncio

from config.settings import CAMERAS_CONFIG, MONGO_DB_NAME, MONGO_URI

logger = logging.getLogger(__name__)

_sync_client: MongoClient | None = None
_async_client: motor.motor_asyncio.AsyncIOMotorClient | None = None


# ---------------------------------------------------------------------------
# Client accessors
# ---------------------------------------------------------------------------


def get_sync_db(db_name: str = MONGO_DB_NAME) -> Database:
    global _sync_client
    if _sync_client is None:
        _sync_client = MongoClient(MONGO_URI)
        logger.info("PyMongo connected: %s / %s", MONGO_URI, db_name)
    return _sync_client[db_name]


def get_async_db(db_name: str = MONGO_DB_NAME):
    global _async_client
    if _async_client is None:
        _async_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        logger.info("Motor connected: %s / %s", MONGO_URI, db_name)
    return _async_client[db_name]


# ---------------------------------------------------------------------------
# Index bootstrap
# ---------------------------------------------------------------------------


def ensure_indexes(db_name: str = MONGO_DB_NAME) -> None:
    db = get_sync_db(db_name)
    db.events.create_index([("timestamp", pymongo.DESCENDING)])
    db.events.create_index([("camera_id", pymongo.ASCENDING)])
    db.events.create_index([("status", pymongo.ASCENDING)])
    db.suppressed_detections.create_index([("timestamp", pymongo.DESCENDING)])
    db.suppressed_detections.create_index([("camera_id", pymongo.ASCENDING)])
    db.suppressed_detections.create_index([("reason", pymongo.ASCENDING)])
    logger.info("MongoDB indexes ensured on '%s'", db_name)


# ---------------------------------------------------------------------------
# Events CRUD
# ---------------------------------------------------------------------------


def insert_event(doc: dict[str, Any], db_name: str = MONGO_DB_NAME) -> str:
    result = get_sync_db(db_name).events.insert_one(doc)
    return str(result.inserted_id)


def insert_suppressed(doc: dict[str, Any], db_name: str = MONGO_DB_NAME) -> str:
    result = get_sync_db(db_name).suppressed_detections.insert_one(doc)
    return str(result.inserted_id)


def find_events(
    camera_id: str | None = None,
    since: datetime | None = None,
    limit: int = 100,
    db_name: str = MONGO_DB_NAME,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if camera_id:
        query["camera_id"] = camera_id
    if since:
        query["timestamp"] = {"$gte": since}
    return list(
        get_sync_db(db_name)
        .events.find(query)
        .sort("timestamp", pymongo.DESCENDING)
        .limit(limit)
    )


# ---------------------------------------------------------------------------
# Config seeding
# ---------------------------------------------------------------------------


def seed_from_config(
    config_path: Path = CAMERAS_CONFIG, db_name: str = MONGO_DB_NAME
) -> None:
    """Upsert cameras, zones, and rules collections from cameras.yaml."""
    with open(config_path) as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    db = get_sync_db(db_name)

    for cam in raw.get("cameras", []):
        cam_id: str = cam["id"]

        # cameras collection uses cameraId (string field) as the unique key,
        # not _id, to match the existing schema used by other services.
        db.cameras.update_one(
            {"cameraId": cam_id},
            {
                "$set": {
                    "cameraId": cam_id,
                    "name": cam["name"],
                    "rtspUrl": cam["rtsp_url"],
                    "locationType": cam["location_type"],
                    "enabled": cam.get("enabled", True),
                }
            },
            upsert=True,
        )

        polygon = cam.get("zone", {}).get("polygon")
        if polygon:
            db.zones.update_one(
                {"_id": f"{cam_id}_zone"},
                {
                    "$set": {
                        "_id": f"{cam_id}_zone",
                        "camera_id": cam_id,
                        "zone_name": "default",
                        "polygon": polygon,
                    }
                },
                upsert=True,
            )

        r = cam.get("rules", {})
        db.rules.update_one(
            {"_id": f"{cam_id}_rules"},
            {
                "$set": {
                    "_id": f"{cam_id}_rules",
                    "camera_id": cam_id,
                    "active_hours_start": r.get("active_hours_start", "00:00"),
                    "active_hours_end": r.get("active_hours_end", "23:59"),
                    "sensitivity": float(r.get("sensitivity", 0.4)),
                    "suppressed_classes": r.get("suppressed_classes", []),
                }
            },
            upsert=True,
        )

    logger.info(
        "Seeded %d camera(s) from %s into '%s'",
        len(raw.get("cameras", [])),
        config_path,
        db_name,
    )
