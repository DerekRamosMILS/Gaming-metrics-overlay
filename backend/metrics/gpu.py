"""
Métricas de GPU: uso, temperatura y VRAM.

Cadena de fallback para uso:
  1. pynvml (NVML) — NVIDIA con nvml.dll instalado
  2. WMI root\\OpenHardwareMonitor — NVIDIA/AMD/Intel, requiere LHM corriendo
  3. PDH Windows Perf Counters — AMD/Intel/NVIDIA sin software externo (uso solo)
  4. None para valores no disponibles

Temperatura:
  1. NVML (NVIDIA) o LHM WMI (cualquier GPU)
  2. ADL PMLog sensor ID 2 — AMD con atiadlxx.dll (RX 6700 XT verificado)
  3. None
"""
import re
import time
import ctypes
import threading
from typing import Optional, Dict, Any

# ── NVML (NVIDIA) ─────────────────────────────────────────────────────────────
_nvml_initialized = False
_nvml_handle = None


def _init_nvml() -> bool:
    global _nvml_initialized, _nvml_handle
    if _nvml_initialized:
        return _nvml_handle is not None
    _nvml_initialized = True
    try:
        from pynvml import nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex  # type: ignore
        nvmlInit()
        if nvmlDeviceGetCount() > 0:
            _nvml_handle = nvmlDeviceGetHandleByIndex(0)
            return True
    except Exception:
        pass
    return False


def _get_nvml_metrics() -> Optional[Dict[str, Any]]:
    if not _init_nvml():
        return None
    try:
        from pynvml import (  # type: ignore
            nvmlDeviceGetUtilizationRates, nvmlDeviceGetTemperature,
            nvmlDeviceGetMemoryInfo, nvmlDeviceGetName, NVML_TEMPERATURE_GPU
        )
        util = nvmlDeviceGetUtilizationRates(_nvml_handle)
        temp = nvmlDeviceGetTemperature(_nvml_handle, NVML_TEMPERATURE_GPU)
        mem  = nvmlDeviceGetMemoryInfo(_nvml_handle)
        name = nvmlDeviceGetName(_nvml_handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8")
        return {
            "usage": float(util.gpu),
            "temp":  float(temp),
            "vram_used_mb":  round(mem.used  / 1024 ** 2),
            "vram_total_mb": round(mem.total / 1024 ** 2),
            "name": name,
        }
    except Exception:
        return None


# ── LibreHardwareMonitor WMI ──────────────────────────────────────────────────
def _get_lhm_metrics() -> Optional[Dict[str, Any]]:
    try:
        import wmi  # type: ignore
        w = wmi.WMI(namespace=r"root\OpenHardwareMonitor")
        usage = temp = vram_used = vram_total = None
        for s in w.Sensor():
            st, sn = s.SensorType, s.Name.upper()
            if st == "Load"        and "GPU CORE"        in sn: usage      = round(float(s.Value), 1)
            elif st == "Temperature" and "GPU CORE"      in sn: temp       = round(float(s.Value), 1)
            elif st == "SmallData"  and "GPU MEMORY USED"  in sn: vram_used  = round(float(s.Value))
            elif st == "SmallData"  and "GPU MEMORY TOTAL" in sn: vram_total = round(float(s.Value))
        if usage is not None or temp is not None:
            return {"usage": usage, "temp": temp,
                    "vram_used_mb": vram_used, "vram_total_mb": vram_total, "name": "GPU"}
    except Exception:
        pass
    return None


# ── AMD ADL QueryPMLogData (GPU temperature, one-shot) ────────────────────────
#
# ADL2_New_QueryPMLogData_Get devuelve un snapshot de todas las métricas GPU.
# La estructura ADLSingleSensorData tiene los campos en orden (value, active),
# verificado empíricamente en RDNA2 (RX 6700 XT).
#
# Índices confirmados (0-based, mapeados al SMU metrics struct de RDNA2):
#   sensors[7]  = TemperatureEdge    (°C)
#   sensors[26] = TemperatureHotspot (°C) — respaldo
#
# ADL_CONTEXT_HANDLE se inicializa una sola vez y se reutiliza.

class _ADLSensorData(ctypes.Structure):
    # Orden REAL verificado: value primero, luego flag active
    _fields_ = [("value", ctypes.c_int), ("active", ctypes.c_int)]


class _ADLPMLogDataOutput(ctypes.Structure):
    _fields_ = [
        ("iActiveSampleRate", ctypes.c_int),
        ("iTimeStamp",        ctypes.c_longlong),
        ("sensors",           _ADLSensorData * 256),
    ]

# Índice 0-based → TemperatureEdge (°C)  [verificado: devuelve ~70°C en RX 6700 XT]
_ADL_SENSOR_EDGE_IDX     = 7
# Índice 0-based → TemperatureHotspot (°C)  [verificado: devuelve ~85°C]
_ADL_SENSOR_HOTSPOT_IDX  = 26


class _ADLTempReader:
    """
    Lee temperatura de GPU AMD vía ADL2_New_QueryPMLogData_Get (atiadlxx.dll).
    Inicialización en hilo de fondo; cada llamada a get_temp() hace una query
    fresca (la función es barata, no requiere streaming previo).
    """

    def __init__(self):
        self._lock  = threading.Lock()
        self._ctx   = None
        self._adl   = None
        self._ready = False
        self._cb    = None   # ancla GC del callback de memoria
        self._bufs: list = []
        # Retraso de 3 s: escalonado respecto al CLR para no acumular carga al arrancar
        def _delayed():
            import time; time.sleep(3); self._init()
        threading.Thread(target=_delayed, daemon=True, name="adl-temp-init").start()

    def _init(self) -> None:
        try:
            adl = ctypes.CDLL("atiadlxx.dll")
            _ALLOC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int)
            bufs: list = []

            def _alloc_cb(n: int) -> int:
                b = (ctypes.c_byte * n)()
                bufs.append(b)
                return ctypes.addressof(b)

            cb = _ALLOC(_alloc_cb)
            ctx = ctypes.c_void_p()
            if adl.ADL2_Main_Control_Create(cb, 1, ctypes.byref(ctx)) != 0:
                return

            # Verifica que la función exista y devuelva algo coherente
            out = _ADLPMLogDataOutput()
            r = adl.ADL2_New_QueryPMLogData_Get(ctx, 0, ctypes.byref(out))
            if r != 0:
                return

            with self._lock:
                self._adl   = adl
                self._ctx   = ctx
                self._cb    = cb
                self._bufs  = bufs
                self._ready = True
        except Exception:
            pass

    def get_temp(self) -> Optional[float]:
        """Retorna temperatura edge de la GPU en °C, o None si no disponible."""
        with self._lock:
            if not self._ready:
                return None
            adl, ctx = self._adl, self._ctx
        try:
            out = _ADLPMLogDataOutput()
            if adl.ADL2_New_QueryPMLogData_Get(ctx, 0, ctypes.byref(out)) != 0:
                return None
            # Temperatura edge (índice 7) — rango válido 1–130°C
            v = out.sensors[_ADL_SENSOR_EDGE_IDX].value
            if 1 <= v <= 130:
                return float(v)
            # Respaldo: hotspot (índice 26)
            v2 = out.sensors[_ADL_SENSOR_HOTSPOT_IDX].value
            if 1 <= v2 <= 130:
                return float(v2)
        except Exception:
            pass
        return None


_adl_reader = _ADLTempReader()


# ── PDH Windows Performance Counters (AMD / Intel / NVIDIA sin driver NVML) ───
class _PDHGPUCounter:
    """
    Lee el uso de GPU sumando las instancias del motor 3D vía PDH.
    Funciona para AMD, Intel y NVIDIA sin software externo.
    Solo uso (no temperatura).
    """
    REINIT_EVERY = 30   # Re-enumera instancias cada N lecturas
    _INIT_DELAY_S = 5   # Espera antes de la primera query WMI (evita freeze al arrancar)

    def __init__(self):
        self._lock      = threading.Lock()
        self._query     = None
        self._handles: list = []
        self._luid:     Optional[str] = None
        self._calls     = 0
        self._ready_at  = time.monotonic() + self._INIT_DELAY_S

    def _find_luid(self) -> Optional[str]:
        """Encuentra la LUID de la GPU discreta (mayor memoria dedicada)."""
        try:
            import wmi  # type: ignore
            w = wmi.WMI(namespace="root/cimv2")
            best_luid, best_mem = None, 0
            for a in w.Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory():
                mem = int(getattr(a, "DedicatedUsage", 0) or 0)
                if mem > best_mem:
                    m = re.search(r"luid_0x[0-9a-fA-F]+_0x[0-9a-fA-F]+", a.Name)
                    if m:
                        best_luid, best_mem = m.group(0), mem
            return best_luid
        except Exception:
            return None

    def _setup(self) -> bool:
        try:
            import win32pdh  # type: ignore
            if self._query:
                try:
                    win32pdh.CloseQuery(self._query)
                except Exception:
                    pass
                self._query = None

            if not self._luid:
                self._luid = self._find_luid()
            if not self._luid:
                return False

            items = win32pdh.EnumObjectItems(None, None, "GPU Engine", win32pdh.PERF_DETAIL_WIZARD)
            instances = items[1]

            q = win32pdh.OpenQuery()
            handles = []
            for inst in instances:
                if "engtype_3D" not in inst or self._luid not in inst:
                    continue
                try:
                    path = win32pdh.MakeCounterPath(
                        (None, "GPU Engine", inst, None, 0, "Utilization Percentage")
                    )
                    handles.append(win32pdh.AddCounter(q, path))
                except Exception:
                    pass

            if not handles:
                win32pdh.CloseQuery(q)
                return False

            self._query   = q
            self._handles = handles
            win32pdh.CollectQueryData(q)   # Primera muestra base para contadores de tasa
            return True
        except Exception:
            return False

    def get_usage(self) -> Optional[float]:
        with self._lock:
            if time.monotonic() < self._ready_at:
                return None  # Aún en periodo de delay inicial
            self._calls += 1
            needs_init = (self._query is None) or (self._calls % self.REINIT_EVERY == 0)
            if needs_init and not self._setup():
                return None
            try:
                import win32pdh  # type: ignore
                win32pdh.CollectQueryData(self._query)
                total = 0.0
                for h in self._handles:
                    try:
                        _, val = win32pdh.GetFormattedCounterValue(h, win32pdh.PDH_FMT_DOUBLE)
                        total += val
                    except Exception:
                        pass
                return round(min(total, 100.0), 1)
            except Exception:
                self._query = None
                return None


_pdh_counter = _PDHGPUCounter()


# ── API pública ───────────────────────────────────────────────────────────────
def get_metrics() -> Dict[str, Any]:
    """Retorna métricas de GPU con fallback automático."""
    # 1. NVML — NVIDIA con driver completo
    result = _get_nvml_metrics()
    if result:
        return result

    # 2. LibreHardwareMonitor — cualquier GPU, con temp
    result = _get_lhm_metrics()
    if result:
        return result

    # 3. PDH (uso) + ADL PMLog (temp) — AMD/Intel/NVIDIA sin software externo
    usage = _pdh_counter.get_usage()
    temp  = _adl_reader.get_temp()
    return {
        "usage": usage,
        "temp":  temp,
        "vram_used_mb":  None,
        "vram_total_mb": None,
        "name": "GPU",
    }
