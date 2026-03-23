"""
Servidor WebSocket local para comunicar backend con el overlay de Electron.

- Puerto: 29874 (configurable)
- Protocolo: JSON sobre WebSocket
- Mensajes del servidor → cliente: métricas en tiempo real
- Mensajes del cliente → servidor: comandos (toggle, update_config, etc.)

Formato de mensaje de métricas:
{
  "type": "metrics",
  "data": { ... }
}

Comandos del cliente:
{
  "type": "command",
  "action": "toggle" | "update_config" | "get_config",
  "payload": { ... }  // opcional
}
"""
import asyncio
import json
import logging
from typing import Set, Callable, Optional

import websockets  # type: ignore
from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)

WS_PORT = 29874
WS_HOST = "127.0.0.1"


class OverlayServer:
    """
    Servidor WebSocket que:
    - Broadcast métricas a todos los clientes conectados
    - Recibe comandos y los despacha via callbacks
    """

    def __init__(self, port: int = WS_PORT):
        self._port = port
        self._clients: Set[WebSocketServerProtocol] = set()
        self._on_command: Optional[Callable] = None
        self._server = None
        self._running = False

    def set_command_handler(self, handler: Callable) -> None:
        """Registra el handler para comandos entrantes del cliente."""
        self._on_command = handler

    async def broadcast(self, message: dict) -> None:
        """Envía un mensaje JSON a todos los clientes conectados."""
        if not self._clients:
            return
        data = json.dumps(message, ensure_ascii=False)
        disconnected = set()
        for ws in self._clients.copy():
            try:
                await ws.send(data)
            except websockets.ConnectionClosed:
                disconnected.add(ws)
            except Exception as e:
                logger.debug(f"[WS] Error al enviar a cliente: {e}")
                disconnected.add(ws)
        self._clients -= disconnected

    async def _handle_client(self, ws: WebSocketServerProtocol) -> None:
        """Maneja la conexión de un cliente."""
        self._clients.add(ws)
        client_addr = ws.remote_address
        logger.info(f"[WS] Cliente conectado: {client_addr}")

        try:
            async for raw_msg in ws:
                if not raw_msg:
                    continue
                try:
                    msg = json.loads(raw_msg)
                    if msg.get("type") == "command" and self._on_command:
                        await self._on_command(msg)
                except json.JSONDecodeError:
                    logger.warning(f"[WS] Mensaje inválido recibido: {raw_msg[:100]}")
        except websockets.ConnectionClosed:
            pass
        except Exception as e:
            logger.debug(f"[WS] Error en cliente {client_addr}: {e}")
        finally:
            self._clients.discard(ws)
            logger.info(f"[WS] Cliente desconectado: {client_addr}")

    async def start(self) -> None:
        """Inicia el servidor WebSocket y bloquea hasta que se detenga."""
        self._running = True
        logger.info(f"[WS] Servidor iniciando en ws://{WS_HOST}:{self._port}")
        async with websockets.serve(
            self._handle_client,
            WS_HOST,
            self._port,
            ping_interval=20,
            ping_timeout=20,
            max_size=1_048_576,  # 1 MB max mensaje
        ) as server:
            self._server = server
            logger.info(f"[WS] Servidor activo en ws://{WS_HOST}:{self._port}")
            await asyncio.Future()  # Espera indefinidamente

    @property
    def client_count(self) -> int:
        return len(self._clients)
