"""FastAPI application entry point.

Run with:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

OpenAPI docs available at http://localhost:8000/docs
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.cameras import router as cameras_router
from backend.routes.events import router as events_router
from backend.routes.stats import router as stats_router
from backend.routes.ws import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="PIDS POC API",
    description="Perimeter Intrusion Detection System — FastAPI backend",
    version="0.5.0",
)

# CORS — allow the Angular dev server and any localhost origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cameras_router)
app.include_router(events_router)
app.include_router(stats_router)
app.include_router(ws_router)


@app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "service": "PIDS POC API"}
