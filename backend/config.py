"""
Gestión de configuración persistente en JSON.
"""
import json
import os
from dataclasses import dataclass, asdict, field
from typing import Optional

import sys

def get_base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_FILE = os.path.join(get_base_dir(), "config.json")

DEFAULT_CONFIG = {
    "metrics": {
        "fps": True,
        "cpu_usage": True,
        "cpu_temp": True,
        "gpu_usage": True,
        "gpu_temp": True,
        "ram_usage": True,
        "clock": True
    },
    "display": {
        "position": "top-right",
        "opacity": 0.85,
        "font_size": 14,
        "hotkey": "alt+f10",
        "update_interval": 1000,
        "visible": True
    }
}


def load_config() -> dict:
    """Carga configuración desde disco, usando defaults si no existe."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Merge con defaults para cubrir claves nuevas
            config = _deep_merge(DEFAULT_CONFIG.copy(), data)
            return config
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Persiste configuración en disco."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"[Config] Error al guardar: {e}")


def _deep_merge(base: dict, override: dict) -> dict:
    """Fusiona override sobre base de forma recursiva."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
