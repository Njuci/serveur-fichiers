"""WebSocket /ws : notifications en temps réel.

Les navigateurs ne peuvent pas envoyer d'en-tête Authorization sur un
WebSocket : le jeton est donc passé dans l'URL (/ws?token=...) et vérifié
AVANT d'accepter la connexion.
"""

from fastapi import APIRouter, Query, WebSocket, status

from ..dependencies import user_from_token
from ..services.notifier import notifier

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = Query(default=None)):
    user = user_from_token(token) if token else None
    if user is None:
        # Fermer avant accept() : le serveur répond 403 à la poignée de main.
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await notifier.connect(websocket)
    try:
        # Le canal est surtout descendant (serveur -> client). On continue à lire
        # pour détecter la déconnexion ; les messages reçus sont ignorés.
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    finally:
        notifier.disconnect(websocket)
