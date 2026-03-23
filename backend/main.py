"""
Punto de entrada del backend del overlay.

Arquitectura de threads:
  Thread principal → asyncio event loop (WebSocket server + metrics broadcast)
  Thread secundario → pystray (system tray icon, requiere su propio loop)
  Thread terciario → keyboard (hotkey listener global)

El backend NO tiene ventana propia; toda la UI está en el proceso Electron.
"""
import asyncio
import json
import logging
import subprocess
import sys
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# Añade el directorio padre al path para imports relativos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_config, save_config
from metrics.collector import MetricsCollector
from server.ws_server import OverlayServer
from tray.tray_app import TrayApp

# ── Logging ────────────────────────────────────────────────────────────────────
log_level = logging.DEBUG if "--debug" in sys.argv else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("overlay.main")

# ── Estado global ──────────────────────────────────────────────────────────────
config = load_config()
overlay_visible = config["display"].get("visible", True)
loop: asyncio.AbstractEventLoop = None
server: OverlayServer = None
collector: MetricsCollector = None
tray: TrayApp = None
electron_process: subprocess.Popen = None
shutdown_event = threading.Event()


# ── Gestión del proceso Electron ───────────────────────────────────────────────
def get_base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find_electron_exe() -> str:
    """Busca el ejecutable de Electron en la carpeta frontend."""
    base = get_base_dir()
    if getattr(sys, 'frozen', False):
        candidates = [
            os.path.join(base, "frontend", "OverlayMils.exe"),
            os.path.join(base, "OverlayMils.exe"),
        ]
    else:
        candidates = [
            os.path.join(base, "frontend", "dist", "win-unpacked", "OverlayMils.exe"),
            os.path.join(base, "frontend", "node_modules", "electron", "dist", "electron.exe"),
            os.path.join(base, "frontend", "node_modules", ".bin", "electron.cmd"),
            os.path.join(base, "frontend", "node_modules", ".bin", "electron"),
            "electron",
        ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[-1]


def launch_electron() -> None:
    """Lanza el proceso Electron del overlay."""
    global electron_process
    electron_exe = _find_electron_exe()

    if getattr(sys, 'frozen', False):
        frontend_dir = os.path.dirname(electron_exe)
        args = [electron_exe]
    else:
        base = get_base_dir()
        frontend_dir = os.path.join(base, "frontend")
        args = [electron_exe, "."]

    if not os.path.exists(frontend_dir):
        logger.error(f"[Main] No se encontró el directorio frontend: {frontend_dir}")
        return

    try:
        logger.info(f"[Main] Lanzando Electron: {electron_exe}")
        electron_process = subprocess.Popen(
            args,
            cwd=frontend_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        logger.info(f"[Main] Electron PID: {electron_process.pid}")
    except (FileNotFoundError, OSError) as e:
        logger.error(f"[Main] No se pudo lanzar Electron: {e}")
        logger.error("[Main] Ejecuta 'npm install' en la carpeta frontend primero.")


def stop_electron() -> None:
    """Detiene el proceso Electron y todo su árbol de procesos hijos."""
    global electron_process
    if electron_process and electron_process.poll() is None:
        pid = electron_process.pid
        logger.info(f"[Main] Deteniendo Electron (PID {pid})...")
        # taskkill /T mata el proceso Y todos sus hijos (renderer, GPU process, etc.)
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5
            )
        except Exception:
            electron_process.kill()
        electron_process = None


# ── Handlers de comandos WebSocket ────────────────────────────────────────────
async def handle_command(msg: dict) -> None:
    """Procesa comandos entrantes desde el cliente Electron."""
    global config, overlay_visible

    action = msg.get("action", "")
    payload = msg.get("payload", {})

    logger.debug(f"[Main] Comando recibido: {action}")

    if action == "toggle":
        overlay_visible = not overlay_visible
        config["display"]["visible"] = overlay_visible
        save_config(config)
        if tray:
            tray.update_visibility(overlay_visible)
        await server.broadcast({"type": "visibility", "visible": overlay_visible})

    elif action == "update_config":
        if payload:
            config = _deep_merge(config, payload)
            save_config(config)
            collector.update_config(config)
            await server.broadcast({"type": "config", "data": config})

    elif action == "get_config":
        await server.broadcast({"type": "config", "data": config})

    elif action == "quit":
        logger.info("[Main] Salida solicitada desde el overlay")
        if tray:
            tray.stop()
        _shutdown()

    elif action == "set_visibility":
        overlay_visible = bool(payload.get("visible", True))
        config["display"]["visible"] = overlay_visible
        save_config(config)
        if tray:
            tray.update_visibility(overlay_visible)


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ── Loop de broadcast de métricas ─────────────────────────────────────────────
async def metrics_broadcast_loop() -> None:
    """Recolecta métricas y las envía a todos los clientes periódicamente."""
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="metrics")
    logger.info("[Main] Loop de métricas iniciado")

    while True:
        interval_ms = config["display"].get("update_interval", 1000)
        interval_s = max(0.1, interval_ms / 1000.0)

        try:
            # Ejecuta la recolección en un thread separado para no bloquear asyncio
            metrics = await asyncio.get_event_loop().run_in_executor(
                executor, collector.collect
            )

            if server.client_count > 0:
                await server.broadcast({"type": "metrics", "data": metrics})

        except Exception as e:
            logger.debug(f"[Main] Error en broadcast: {e}")

        await asyncio.sleep(interval_s)


# Hotkeys manejados por Electron (globalShortcut) — no se necesita keyboard module


# ── Tray callbacks ────────────────────────────────────────────────────────────
def on_tray_toggle(visible: bool) -> None:
    """Llamado desde el tray cuando el usuario hace click en toggle."""
    global overlay_visible
    overlay_visible = visible
    config["display"]["visible"] = visible
    save_config(config)
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(
            server.broadcast({"type": "visibility", "visible": visible}),
            loop
        )


def on_tray_quit() -> None:
    """Llamado desde el tray cuando el usuario elige Salir."""
    logger.info("[Main] Salida solicitada desde tray")
    _shutdown()


def on_tray_config() -> None:
    """Abre la ventana de configuración en Electron."""
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(
            server.broadcast({"type": "open_config"}),
            loop
        )


# ── Shutdown ──────────────────────────────────────────────────────────────────
def _shutdown() -> None:
    """Secuencia limpia de cierre."""
    if shutdown_event.is_set():
        return  # Ya en proceso de cierre
    logger.info("[Main] Iniciando shutdown...")

    # 1. Dice a Electron que se cierre vía WebSocket (app.quit() es la forma correcta)
    if server and loop and loop.is_running():
        try:
            future = asyncio.run_coroutine_threadsafe(
                server.broadcast({"type": "quit"}), loop
            )
            future.result(timeout=1)  # Espera max 1 s a que se envíe
        except Exception:
            pass
        time.sleep(0.4)  # Breve pausa para que Electron reciba el mensaje

    # 2. Mata Electron
    collector.stop()
    stop_electron()
    shutdown_event.set()

    if loop and loop.is_running():
        async def _cancel_all():
            tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
            for t in tasks:
                t.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            loop.stop()
        asyncio.run_coroutine_threadsafe(_cancel_all(), loop)


# ── Main ──────────────────────────────────────────────────────────────────────
async def _async_main() -> None:
    """Cuerpo principal del event loop de asyncio."""
    global server, collector

    # Inicializa el recolector de métricas
    collector = MetricsCollector(config)
    collector.start()

    # Inicia el servidor WebSocket
    server = OverlayServer()
    server.set_command_handler(handle_command)

    # Arranca el loop de métricas en paralelo con el servidor
    await asyncio.gather(
        server.start(),
        metrics_broadcast_loop(),
    )


def main() -> None:
    global loop, tray

    logger.info("=" * 50)
    logger.info("  Overlay Videojuegos - Backend")
    logger.info("=" * 50)

    # Lanza Electron en un hilo separado
    electron_thread = threading.Thread(target=launch_electron, daemon=True)
    electron_thread.start()

    # Prepara el tray (se ejecutará en el thread principal después del loop asyncio)
    tray = TrayApp(
        on_toggle=on_tray_toggle,
        on_quit=on_tray_quit,
        on_open_config=on_tray_config,
    )

    # Crea y arranca el event loop de asyncio en un hilo separado
    loop = asyncio.new_event_loop()

    def run_async():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_async_main())
        except Exception as e:
            logger.error(f"[Main] Error en event loop: {e}")
        finally:
            loop.close()

    async_thread = threading.Thread(target=run_async, daemon=True, name="asyncio-main")
    async_thread.start()

    # El tray DEBE correr en el thread principal (requerimiento de Windows)
    try:
        tray.run()
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown()
        shutdown_event.wait(timeout=5)
        logger.info("[Main] Backend terminado")
        os._exit(0)  # Fuerza la salida completa del proceso (libera hooks de teclado, etc.)


if __name__ == "__main__":
    main()
