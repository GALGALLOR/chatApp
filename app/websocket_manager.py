import asyncio
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[user_id].add(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(user_id)
            if connections is None:
                return
            connections.discard(websocket)
            if not connections:
                self._connections.pop(user_id, None)

    async def is_online(self, user_id: int) -> bool:
        async with self._lock:
            return bool(self._connections.get(user_id))

    async def send_to_user(self, user_id: int, payload: dict) -> int:
        async with self._lock:
            connections = list(self._connections.get(user_id, set()))

        delivered = 0
        for websocket in connections:
            try:
                await websocket.send_json(payload)
                delivered += 1
            except Exception:
                await self.disconnect(user_id, websocket)
        return delivered


manager = ConnectionManager()

