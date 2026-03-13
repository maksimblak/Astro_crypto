"""WebSocket endpoint for real-time dashboard updates."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("astrobtc.ws")

router = APIRouter()

_connections: Set[WebSocket] = set()
_connections_lock = asyncio.Lock()


async def _add(ws: WebSocket) -> None:
    async with _connections_lock:
        _connections.add(ws)
    logger.info("WS client connected (%d total)", len(_connections))


async def _remove(ws: WebSocket) -> None:
    async with _connections_lock:
        _connections.discard(ws)
    logger.info("WS client disconnected (%d total)", len(_connections))


async def broadcast(event: str, data: dict | None = None) -> int:
    """Broadcast a JSON message to all connected clients.

    Returns the number of clients that received the message.
    """
    message = json.dumps({"event": event, "data": data or {}})
    sent = 0
    dead: list[WebSocket] = []

    async with _connections_lock:
        clients = list(_connections)

    for ws in clients:
        try:
            await ws.send_text(message)
            sent += 1
        except Exception:
            dead.append(ws)

    if dead:
        async with _connections_lock:
            for ws in dead:
                _connections.discard(ws)

    return sent


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    await _add(ws)
    try:
        while True:
            # Keep connection alive, handle pings from client
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WS error", exc_info=True)
    finally:
        await _remove(ws)
