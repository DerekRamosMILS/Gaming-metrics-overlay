"""
Aggregador central de métricas.

Recolecta todas las métricas en un solo dict JSON-serializable,
respetando la configuración de qué métricas están activas.
"""
import time
from datetime import datetime
from typing import Dict, Any

from . import cpu, gpu, ram


class MetricsCollector:
    """
    Recolecta métricas del sistema de forma eficiente.
    Diseñado para llamarse periódicamente desde el event loop de asyncio.
    """

    def __init__(self, config: dict):
        self._config = config
        self._metrics_cfg = config.get("metrics", {})
        self._started = False

    def start(self) -> None:
        """Inicializa recursos que requieren start explícito."""
        if not self._started:
            # Primer llamado a cpu_percent retorna 0.0; este lo descarta
            import psutil as _psutil
            _psutil.cpu_percent(interval=None)
            self._started = True

    def stop(self) -> None:
        """Libera recursos."""
        self._started = False

    def update_config(self, config: dict) -> None:
        """Actualiza configuración en caliente."""
        self._config = config
        self._metrics_cfg = config.get("metrics", {})

    def collect(self) -> Dict[str, Any]:
        """
        Recolecta todas las métricas habilitadas y las retorna como dict.
        Este método es síncrono y puede llamarse desde un executor de asyncio.
        """
        cfg = self._metrics_cfg
        result: Dict[str, Any] = {
            "timestamp": time.time(),
        }

        # CPU
        cpu_data = {}
        if cfg.get("cpu_usage", True):
            cpu_data["usage"] = cpu.get_usage()
        if cfg.get("cpu_temp", True):
            cpu_data["temp"] = cpu.get_temperature()
        if cpu_data:
            result["cpu"] = cpu_data

        # GPU
        if cfg.get("gpu_usage", True) or cfg.get("gpu_temp", True):
            gpu_data = gpu.get_metrics()
            filtered = {}
            if cfg.get("gpu_usage", True):
                filtered["usage"] = gpu_data.get("usage")
            if cfg.get("gpu_temp", True):
                filtered["temp"] = gpu_data.get("temp")
            filtered["vram_used_mb"] = gpu_data.get("vram_used_mb")
            filtered["vram_total_mb"] = gpu_data.get("vram_total_mb")
            filtered["name"] = gpu_data.get("name", "GPU")
            result["gpu"] = filtered

        # RAM
        if cfg.get("ram_usage", True):
            result["ram"] = ram.get_metrics()

        # Hora — formato 12h sin AM/PM, sin segundos (ej: 5:11)
        if cfg.get("clock", True):
            now = datetime.now()
            hour12 = now.hour % 12 or 12
            result["clock"] = f"{hour12}:{now.strftime('%M')}"

        return result
