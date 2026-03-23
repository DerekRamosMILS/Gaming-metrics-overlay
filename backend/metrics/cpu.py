"""
Métricas de CPU: uso porcentual y temperatura.

Cadena de fallback para temperatura:
  1. LibreHardwareMonitor DLL (pythonnet) — lee temps AMD/Intel sin app externa
  2. psutil.sensors_temperatures() — funciona en algunos sistemas
  3. WMI namespace root\\OpenHardwareMonitor — requiere LHM/OHM corriendo
  4. WMI MSAcpi_ThermalZoneTemperature — disponible en la mayoría de sistemas
  5. Win32_PerfFormattedData_Counters_ThermalZoneInformation
"""
import os
import sys
import threading
import psutil
from typing import Optional

def get_base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_LHM_DLL_PATH = os.path.join(get_base_dir(), "tools")


class _LHMCpuTemp:
    """
    Lee temperatura del CPU vía LibreHardwareMonitorLib.dll (pythonnet).
    Inicialización en hilo de fondo para no bloquear el arranque.
    Requiere que el backend corra con privilegios de administrador.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._computer = None
        self._cpu_hw = None
        self._ready = False
        # Retraso de 10 s: evita que la carga del driver de kernel de LHM
        # congele el sistema mientras el usuario está arrancando la app
        def _delayed():
            import time; time.sleep(10); self._init()
        threading.Thread(target=_delayed, daemon=True, name="lhm-cpu-init").start()

    def _init(self) -> None:
        try:
            if _LHM_DLL_PATH not in sys.path:
                sys.path.insert(0, _LHM_DLL_PATH)

            import clr  # type: ignore
            clr.AddReference("LibreHardwareMonitorLib")

            from LibreHardwareMonitor.Hardware import Computer  # type: ignore

            c = Computer()
            c.IsCpuEnabled = True
            c.Open()

            # Busca el hardware de CPU y verifica que devuelva temperaturas válidas
            cpu_hw = None
            for hw in list(c.Hardware):
                if "cpu" not in str(hw.HardwareType).lower():
                    continue
                try:
                    hw.Update()
                except Exception:
                    continue
                for sensor in list(hw.Sensors):
                    try:
                        if "temperature" not in str(sensor.SensorType).lower():
                            continue
                        val_raw = sensor.Value
                        if val_raw is None:
                            continue
                        v = float(val_raw)
                        # Valor válido y > 0 indica que tenemos privilegios de admin
                        if 0 < v < 150:
                            cpu_hw = hw
                            break
                    except Exception:
                        continue
                if cpu_hw:
                    break

            if cpu_hw is None:
                return

            with self._lock:
                self._computer = c
                self._cpu_hw = cpu_hw
                self._ready = True

        except Exception:
            pass

    def get_temp(self) -> Optional[float]:
        """Retorna la temperatura del paquete CPU en °C, o None si no disponible."""
        with self._lock:
            if not self._ready:
                return None
            hw = self._cpu_hw

        try:
            hw.Update()
        except Exception:
            return None

        package_temp = None
        best_temp = None

        for sensor in list(hw.Sensors):
            try:
                if "temperature" not in str(sensor.SensorType).lower():
                    continue
                val_raw = sensor.Value
                if val_raw is None:
                    continue
                v = float(val_raw)
                if not (0 < v < 150):
                    continue
                name = str(sensor.Name).lower()
                # Prioridad: CPU Package > Tctl/Tdie > cualquier otro
                if "package" in name or "tctl" in name or "tdie" in name:
                    package_temp = round(v, 1)
                elif best_temp is None:
                    best_temp = round(v, 1)
            except Exception:
                continue

        return package_temp if package_temp is not None else best_temp


_lhm_reader = _LHMCpuTemp()


# ── API pública ───────────────────────────────────────────────────────────────

def get_usage() -> float:
    """Retorna uso de CPU en porcentaje (0–100)."""
    return psutil.cpu_percent(interval=None)


def get_temperature() -> Optional[float]:
    """
    Retorna temperatura del CPU en °C.
    Intenta múltiples fuentes de forma graceful.
    """
    # Intento 1: LibreHardwareMonitor DLL (más confiable en AMD/Intel Windows)
    temp = _lhm_reader.get_temp()
    if temp is not None:
        return temp

    # Intento 2: psutil (funciona en Linux/macOS; en Windows requiere hardware específico)
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            priority_keys = ["coretemp", "k10temp", "cpu_thermal", "cpu-thermal"]
            for key in priority_keys:
                if key in temps and temps[key]:
                    return round(temps[key][0].current, 1)
            for name, entries in temps.items():
                if "cpu" in name.lower() and entries:
                    return round(entries[0].current, 1)
    except (AttributeError, Exception):
        pass

    # Intento 3: LibreHardwareMonitor / OpenHardwareMonitor via WMI
    try:
        import wmi  # type: ignore
        w = wmi.WMI(namespace=r"root\OpenHardwareMonitor")
        for sensor in w.Sensor():
            if sensor.SensorType == "Temperature" and "CPU" in sensor.Name:
                return round(float(sensor.Value), 1)
    except Exception:
        pass

    # Intento 4: WMI ACPI Thermal Zone (menos preciso, pero ampliamente disponible)
    try:
        import wmi  # type: ignore
        w = wmi.WMI(namespace=r"root\wmi")
        zones = w.MSAcpi_ThermalZoneTemperature()
        if zones:
            temp_c = (zones[0].CurrentTemperature / 10.0) - 273.15
            if 0 < temp_c < 150:
                return round(temp_c, 1)
    except Exception:
        pass

    # Intento 5: Win32_PerfFormattedData_Counters_ThermalZoneInformation
    try:
        import wmi  # type: ignore
        w = wmi.WMI(namespace=r"root\cimv2")
        zones = w.Win32_PerfFormattedData_Counters_ThermalZoneInformation()
        best = None
        for z in zones:
            val = getattr(z, "Temperature", None)
            if val:
                temp_c = (float(val) / 10.0) - 273.15
                if 0 < temp_c < 150:
                    if best is None or temp_c > best:
                        best = round(temp_c, 1)
        if best is not None:
            return best
    except Exception:
        pass

    return None


def get_metrics() -> dict:
    return {
        "usage": get_usage(),
        "temp": get_temperature(),
    }
