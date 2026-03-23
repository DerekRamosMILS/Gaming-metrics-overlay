PRESENTMON — Contador de FPS
============================

Para activar el contador de FPS, descarga PresentMon y coloca el ejecutable
en esta carpeta (/tools/).

Descarga oficial (Intel):
  https://github.com/GameTechDev/PresentMon/releases

Archivo requerido:
  tools/presentmon.exe   (la versión CLI, no la GUI)

PresentMon usa Event Tracing for Windows (ETW) — la misma tecnología que
usa Windows Game Bar y el Xbox Game Bar para medir FPS.

NOTA: Es posible que requiera ejecutar la app como Administrador para
      acceder a ciertos procesos. Muchos juegos funcionan sin admin.

SEGURIDAD:
  - No usa DLL injection
  - No modifica memoria de procesos
  - Es indetectable por anti-cheat (es una herramienta oficial de Microsoft/Intel)
  - Mismo mecanismo que el Xbox Game Bar overlay

Si no instalas PresentMon, el FPS simplemente mostrará "N/A" en el overlay.
Todas las demás métricas (CPU, GPU, RAM, temperatura) funcionan sin PresentMon.
