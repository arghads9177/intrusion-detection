"""WebSocket endpoint for live alert streaming."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.ws_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/alerts")
async def alerts_ws(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            # Keep the connection alive; the server pushes, client just receives
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
