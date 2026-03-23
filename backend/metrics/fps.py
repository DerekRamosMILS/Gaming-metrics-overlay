"""
Contador de FPS via PresentMon (ETW - Event Tracing for Windows).

PresentMon es la herramienta oficial de Intel para medir FPS sin DLL injection.
Usa Event Tracing for Windows (ETW), el mismo mecanismo que usa Game Bar.

Requisito: presentmon.exe en la carpeta /tools/ o en el PATH del sistema.
Descarga: https://github.com/GameTechDev/PresentMon/releases

Si PresentMon no está disponible, el FPS se reporta como None (N/A en la UI).

SEGURIDAD: ETW es una API pública de Windows, completamente segura y no
detectada por anti-cheat (mismo mecanismo que Windows Performance Recorder).
"""
import subprocess
import threading
import os
import time
import re
from typing import Optional

import sys

def get_base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PRESENTMON_PATH = os.path.join(get_base_dir(), "tools", "presentmon.exe")


class FPSCounter:
    """
    Lanza PresentMon en background y parsea su output CSV para extraer FPS.
    Thread-safe y con cleanup automático.
    """

    def __init__(self):
        self._fps: Optional[float] = None
        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._available = self._check_availability()

    def _check_availability(self) -> bool:
        """Verifica si PresentMon está disponible."""
        if os.path.exists(PRESENTMON_PATH):
            return True
        # También busca en PATH
        try:
            result = subprocess.run(
                ["presentmon.exe", "--version"],
                capture_output=True, timeout=2
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @property
    def is_available(self) -> bool:
        return self._available

    def start(self) -> None:
        """Inicia el proceso de monitoreo en background."""
        if not self._available or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Detiene el monitoreo y limpia el proceso."""
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                pass
            self._process = None

    def _monitor_loop(self) -> None:
        """Loop principal: lanza PresentMon y parsea su CSV output."""
        exe = PRESENTMON_PATH if os.path.exists(PRESENTMON_PATH) else "presentmon.exe"

        # -output_stdout: escribe CSV a stdout
        # -stop_existing_session: evita conflictos si ya hay una sesión activa
        cmd = [
            exe,
            "-output_stdout",
            "-stop_existing_session",
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            # Parsea líneas CSV: ApplicationName,ProcessID,...,msBetweenPresents,...
            header_parsed = False
            fps_col_index = -1

            for line in self._process.stdout:
                if not self._running:
                    break
                line = line.strip()
                if not line:
                    continue

                if not header_parsed:
                    cols = [c.lower() for c in line.split(",")]
                    if "msbetweenpresents" in cols:
                        fps_col_index = cols.index("msbetweenpresents")
                        header_parsed = True
                    continue

                if fps_col_index >= 0:
                    parts = line.split(",")
                    if len(parts) > fps_col_index:
                        try:
                            ms = float(parts[fps_col_index])
                            if ms > 0:
                                self._fps = round(1000.0 / ms, 1)
                        except (ValueError, ZeroDivisionError):
                            pass
        except Exception:
            pass
        finally:
            self._fps = None

    def get_fps(self) -> Optional[float]:
        """Retorna el FPS actual o None si no disponible."""
        return self._fps


# Instancia singleton
_counter = FPSCounter()


def start() -> None:
    _counter.start()


def stop() -> None:
    _counter.stop()


def get_fps() -> Optional[float]:
    return _counter.get_fps()


def is_available() -> bool:
    return _counter.is_available
