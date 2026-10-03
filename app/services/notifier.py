"""Gestion des clients WebSocket connectés et diffusion des événements.

Ce module ne fait aucune authentification : c'est le routeur WebSocket qui
vérifie le jeton avant d'appeler `connect`.
"""

import asyncio
import json

SEND_TIMEOUT_SECONDS = 5


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set = set()

    @property
    def count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket) -> None:
        self._connections.discard(websocket)

    async def _send(self, websocket, message: str) -> bool:
        try:
            await asyncio.wait_for(websocket.send_text(message), SEND_TIMEOUT_SECONDS)
            return True
        except Exception:
            return False

    async def broadcast(self, event: dict) -> None:
        """Envoie `event` (en JSON) à tous les clients ; retire ceux qui ne répondent plus."""
        message = json.dumps(event, ensure_ascii=False)
        targets = list(self._connections)
        results = await asyncio.gather(*(self._send(ws, message) for ws in targets))
        for websocket, delivered in zip(targets, results):
            if not delivered:
                self.disconnect(websocket)


# Instance unique partagée par les routeurs.
notifier = ConnectionManager()
