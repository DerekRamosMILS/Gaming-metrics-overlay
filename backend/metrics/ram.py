"""
Métricas de RAM: uso porcentual y MB usados/totales.
"""
import psutil
from typing import Dict, Any


def get_metrics() -> Dict[str, Any]:
    """Retorna uso de RAM del sistema."""
    mem = psutil.virtual_memory()
    return {
        "usage_percent": round(mem.percent, 1),
        "used_mb": round(mem.used / (1024 ** 2)),
        "total_mb": round(mem.total / (1024 ** 2)),
    }
