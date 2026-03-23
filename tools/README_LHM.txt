LIBREHARDWAREMONITOR — Temperaturas para AMD/Intel
===================================================

Para activar temperaturas en GPUs AMD e Intel (y lectura más precisa en general),
instala LibreHardwareMonitor.

Descarga oficial:
  https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases

Instrucciones:
  1. Descarga LibreHardwareMonitor.zip
  2. Extrae en cualquier carpeta (ej: C:\Programs\LibreHardwareMonitor)
  3. Ejecuta LibreHardwareMonitor.exe
  4. Ve a Options → Run On Windows Startup  (recomendado)
  5. Ve a Options → Start Minimized
  6. Activa las temperaturas que quieras monitorear

LibreHardwareMonitor expone sus datos a través de WMI en el namespace
root\OpenHardwareMonitor, que el backend consulta automáticamente.

GPUs compatibles:
  - NVIDIA (funciona TAMBIÉN con pynvml sin necesidad de LHM)
  - AMD (Radeon RX series, RDNA, Vega)
  - Intel Arc / Intel Integrated Graphics
  - AMD APUs

CPUs compatibles:
  - Intel Core (todas las generaciones)
  - AMD Ryzen / Threadripper
  - Intel Xeon

Si no instalas LHM:
  - NVIDIA: temperaturas funcionan via NVML (automático)
  - AMD/Intel: temperaturas mostrarán "N/A"
  - CPU usage y RAM siempre funcionan via psutil (sin LHM)
