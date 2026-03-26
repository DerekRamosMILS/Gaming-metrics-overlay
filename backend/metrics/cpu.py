"""
Métricas de CPU: uso porcentual y temperatura.

Cadena de fallback para temperatura:
  1. psutil.sensors_temperatures() — funciona en algunos sistemas
  2. WMI namespace root\\OpenHardwareMonitor — requiere LHM/OHM corriendo
  3. WMI MSAcpi_ThermalZoneTemperature — disponible en la mayoría de sistemas
  4. Win32_PerfFormattedData_Counters_ThermalZoneInformation
"""
import psutil
from typing import Optional


# ── API pública ───────────────────────────────────────────────────────────────

def get_usage() -> float:
    """Retorna uso de CPU en porcentaje (0–100)."""
    return psutil.cpu_percent(interval=None)


def get_temperature() -> Optional[float]:
    """
    Retorna temperatura del CPU en °C.
    Intenta múltiples fuentes de forma graceful.
    """
    # Intento 1: psutil (funciona en Linux/macOS; en Windows requiere hardware específico)
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

    # Intento 2: LibreHardwareMonitor / OpenHardwareMonitor via WMI
    try:
        import wmi  # type: ignore
        w = wmi.WMI(namespace=r"root\OpenHardwareMonitor")
        for sensor in w.Sensor():
            if sensor.SensorType == "Temperature" and "CPU" in sensor.Name:
                return round(float(sensor.Value), 1)
    except Exception:
        pass

    # Intento 3: WMI ACPI Thermal Zone (menos preciso, pero ampliamente disponible)
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

    # Intento 4: Win32_PerfFormattedData_Counters_ThermalZoneInformation
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
