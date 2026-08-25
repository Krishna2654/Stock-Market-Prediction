import json
import asyncio
from typing import List, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

class ConnectionManager:
    """
    Manages active WebSocket connections for live price streaming,
    real-time BOS/CHoCH event alerts, and status broadcasts.
    """

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
            
        data = json.dumps(message)
        dead_connections = set()
        
        for connection in list(self.active_connections):
            try:
                await asyncio.wait_for(connection.send_text(data), timeout=1.0)
            except Exception:
                dead_connections.add(connection)
                
        for dead in dead_connections:
            self.active_connections.discard(dead)

ws_manager = ConnectionManager()
ws_router = APIRouter()

@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send initial welcome message
        await websocket.send_json({
            "type": "CONNECTION_ESTABLISHED",
            "message": "Connected to AI Market Structure Live Feed"
        })
        while True:
            data = await websocket.receive_text()
            # Echo or process incoming client pings
            try:
                parsed = json.loads(data)
                if parsed.get("action") == "PING":
                    await websocket.send_json({"type": "PONG"})
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
