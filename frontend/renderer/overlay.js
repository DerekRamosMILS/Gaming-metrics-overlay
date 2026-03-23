/**
 * overlay.js — Renderer del overlay
 *
 * Responsabilidades:
 * - Conectar al WebSocket del backend Python
 * - Renderizar métricas en tiempo real con actualizaciones mínimas del DOM
 * - Gestionar visibilidad y configuración dinámica
 * - Calcular y enviar el tamaño real al proceso principal para reposicionar
 */

'use strict';

// ── WebSocket ──────────────────────────────────────────────────────────────────
const WS_PORT   = 29874;
const WS_URL    = `ws://127.0.0.1:${WS_PORT}`;
const RECONNECT_DELAY_MS = 2000;

let ws = null;
let reconnectDelay = RECONNECT_DELAY_MS;
let reconnectTimer = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 3; // ~6 s sin backend → cierra Electron
let everConnected = false;
let config = null;

// ── Refs al DOM ───────────────────────────────────────────────────────────────
const el = {
  overlay:     document.getElementById('overlay'),
  fps:         document.getElementById('val-fps'),
  cpuUsage:    document.getElementById('val-cpu-usage'),
  cpuTemp:     document.getElementById('val-cpu-temp'),
  gpuUsage:    document.getElementById('val-gpu-usage'),
  gpuTemp:     document.getElementById('val-gpu-temp'),
  ram:         document.getElementById('val-ram'),
  clock:       document.getElementById('val-clock'),
  dot:         document.getElementById('connection-dot'),
  rowFps:      document.getElementById('row-fps'),
  rowCpuUsage: document.getElementById('row-cpu-usage'),
  rowCpuTemp:  document.getElementById('row-cpu-temp'),
  rowGpuUsage: document.getElementById('row-gpu-usage'),
  rowGpuTemp:  document.getElementById('row-gpu-temp'),
  rowRam:      document.getElementById('row-ram'),
  rowClock:    document.getElementById('row-clock'),
};

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Aplica clase de color semántico según el porcentaje */
function applyUsageColor(element, value) {
  element.classList.remove('good', 'warn', 'crit');
  if (value === null || value === undefined) return;
  if (value < 60) element.classList.add('good');
  else if (value < 85) element.classList.add('warn');
  else element.classList.add('crit');
}

/** Aplica clase de color según temperatura */
function applyTempColor(element, value, warnThreshold = 70, critThreshold = 85) {
  element.classList.remove('good', 'warn', 'crit');
  if (value === null || value === undefined) return;
  if (value < warnThreshold) element.classList.add('good');
  else if (value < critThreshold) element.classList.add('warn');
  else element.classList.add('crit');
}

/** Formatea un número o retorna '--' si no hay datos */
function fmt(val, suffix = '', decimals = 0) {
  if (val === null || val === undefined) return '--';
  return Number(val).toFixed(decimals) + suffix;
}

/** Muestra u oculta una fila según la configuración */
function setRowVisible(row, visible) {
  if (visible) {
    row.classList.remove('hidden');
  } else {
    row.classList.add('hidden');
  }
}

/** Actualiza la fuente CSS en el overlay */
function applyFontSize(size) {
  el.overlay.style.setProperty('--font-size', `${size}px`);
}

/** Notifica al main process el tamaño real del overlay para reposicionar */
let resizeDebounce = null;
function notifySize() {
  clearTimeout(resizeDebounce);
  resizeDebounce = setTimeout(() => {
    const rect = el.overlay.getBoundingClientRect();
    window.electronAPI?.resizeOverlay(
      Math.ceil(rect.width) + 4,
      Math.ceil(rect.height) + 4
    );
  }, 50);
}

// ── Renderizado de métricas ───────────────────────────────────────────────────
function renderMetrics(data) {
  // FPS
  if (data.fps !== undefined || data.fps_available !== undefined) {
    const fps = data.fps;
    const avail = data.fps_available !== false;
    if (!avail) {
      el.fps.textContent = 'N/D';
      el.fps.title = 'Coloca presentmon.exe en tools/';
    } else {
      el.fps.textContent = fps !== null ? Math.round(fps) : '--';
      el.fps.title = '';
    }
    el.fps.classList.toggle('fps-low', fps !== null && fps < 30);
  }

  // CPU
  if (data.cpu) {
    const { usage, temp } = data.cpu;
    if (usage !== undefined) {
      el.cpuUsage.textContent = fmt(usage, '%', 1);
      applyUsageColor(el.cpuUsage, usage);
    }
    if (temp !== undefined) {
      el.cpuTemp.textContent = fmt(temp, '°C', 1);
      applyTempColor(el.cpuTemp, temp);
    }
  }

  // GPU
  if (data.gpu) {
    const { usage, temp } = data.gpu;
    if (usage !== undefined) {
      el.gpuUsage.textContent = fmt(usage, '%', 1);
      applyUsageColor(el.gpuUsage, usage);
    }
    if (temp !== undefined) {
      el.gpuTemp.textContent = fmt(temp, '°C', 1);
      applyTempColor(el.gpuTemp, temp);
    }
  }

  // RAM — solo GB usados (ej: "21.9 GB")
  if (data.ram) {
    const { usage_percent, used_mb } = data.ram;
    if (used_mb !== undefined && used_mb !== null) {
      el.ram.textContent = `${(used_mb / 1024).toFixed(1)} GB`;
    } else {
      el.ram.textContent = fmt(usage_percent, '%', 1);
    }
    applyUsageColor(el.ram, usage_percent);
  }

  // Reloj
  if (data.clock) {
    el.clock.textContent = data.clock;
  }
}

// ── Aplicar configuración al overlay ─────────────────────────────────────────
function applyConfig(cfg) {
  if (!cfg) return;
  config = cfg;
  const m = cfg.metrics || {};
  const d = cfg.display || {};

  // Visibilidad de filas
  setRowVisible(el.rowFps,      m.fps !== false);
  setRowVisible(el.rowCpuUsage, m.cpu_usage !== false);
  setRowVisible(el.rowCpuTemp,  m.cpu_temp !== false);
  setRowVisible(el.rowGpuUsage, m.gpu_usage !== false);
  setRowVisible(el.rowGpuTemp,  m.gpu_temp !== false);
  setRowVisible(el.rowRam,      m.ram_usage !== false);
  setRowVisible(el.rowClock,    m.clock !== false);

  // Tamaño de fuente
  if (d.font_size) applyFontSize(d.font_size);

  // Layout: vertical (columna) u horizontal (fila)
  if (d.layout === 'horizontal') {
    el.overlay.classList.add('layout-horizontal');
  } else {
    el.overlay.classList.remove('layout-horizontal');
  }

  // Tema visual
  el.overlay.classList.remove('theme-glass', 'theme-minimal');
  if (d.theme && d.theme !== 'default') {
    el.overlay.classList.add(`theme-${d.theme}`);
  }

  // Colores personalizados via variables CSS
  const c = d.colors || {};
  el.overlay.style.setProperty('--text-primary', c.text  || '#2ecc71');
  el.overlay.style.setProperty('--color-fps',    c.fps   || c.text || '#2ecc71');
  el.overlay.style.setProperty('--color-clock',  c.clock || c.text || '#2ecc71');
  el.overlay.style.setProperty('--color-good',   c.good  || '#2ecc71');
  el.overlay.style.setProperty('--color-warn',   c.warn  || '#f39c12');
  el.overlay.style.setProperty('--color-crit',   c.crit  || '#e74c3c');

  notifySize();
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  setConnectionState('connecting');
  ws = new WebSocket(WS_URL);

  ws.addEventListener('open', () => {
    console.log('[Overlay] WebSocket conectado');
    setConnectionState('connected');
    reconnectDelay = RECONNECT_DELAY_MS;
    reconnectAttempts = 0;
    everConnected = true;

    // Solicita la configuración inicial
    sendCommand('get_config');
  });

  ws.addEventListener('message', (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleMessage(msg);
    } catch (e) {
      console.warn('[Overlay] Mensaje inválido:', e);
    }
  });

  ws.addEventListener('close', () => {
    console.warn('[Overlay] WebSocket desconectado');
    setConnectionState('disconnected');
    scheduleReconnect();
  });

  ws.addEventListener('error', (err) => {
    console.error('[Overlay] WebSocket error:', err);
    setConnectionState('disconnected');
  });
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectAttempts++;
  // Si el backend lleva demasiado tiempo muerto, cierra Electron
  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    console.warn('[Overlay] Backend inaccesible — cerrando Electron');
    window.electronAPI?.quit();
    return;
  }
  reconnectTimer = setTimeout(connect, reconnectDelay);
}

function sendCommand(action, payload = {}) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'command', action, payload }));
  }
}

function setConnectionState(state) {
  if (el.dot) el.dot.className = `connection-dot ${state}`;
}

// ── Handler de mensajes del servidor ─────────────────────────────────────────
function handleMessage(msg) {
  switch (msg.type) {
    case 'metrics':
      renderMetrics(msg.data);
      break;

    case 'config':
      applyConfig(msg.data);
      break;

    case 'visibility': {
      const visible = msg.visible;
      window.electronAPI?.setVisibility(visible);
      break;
    }

    case 'open_config':
      window.electronAPI?.openConfig();
      break;

    case 'quit':
      window.electronAPI?.quit();
      break;

    default:
      // Ignora mensajes desconocidos
      break;
  }
}

// ── Salida completa ───────────────────────────────────────────────────────────
function quitApp() {
  // Notifica al backend para que cierre todo (Electron + Python + tray)
  sendCommand('quit');
  // Como fallback, también notifica al main process directamente
  window.electronAPI?.quit();
}

// ── Lock / Unlock (click-through ↔ arrastrable) ───────────────────────────────
let isLocked = true;       // Arranca bloqueado (click-through)
let isDragging = false;
let dragStartX = 0, dragStartY = 0;
let winStartX = 0, winStartY = 0;
let rafId = null;

function setLocked(locked) {
  isLocked = locked;
  el.overlay.classList.toggle('unlocked', !locked);
}

function setupDrag() {
  el.overlay.addEventListener('mousedown', async (e) => {
    if (isLocked) return;
    if (e.button !== 0) return;

    e.preventDefault();
    isDragging = true;
    dragStartX = e.screenX;
    dragStartY = e.screenY;

    const pos = await window.electronAPI?.getWindowPosition();
    winStartX = pos?.x ?? 0;
    winStartY = pos?.y ?? 0;
  });

  // Mousemove: mueve la ventana en tiempo real (throttled vía rAF)
  document.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    if (rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = null;
      const x = winStartX + (e.screenX - dragStartX);
      const y = winStartY + (e.screenY - dragStartY);
      window.electronAPI?.setWindowPosition(x, y);
    });
  });

  // Mouseup: finaliza arrastre y guarda posición
  document.addEventListener('mouseup', (e) => {
    if (!isDragging) return;
    isDragging = false;
    const x = winStartX + (e.screenX - dragStartX);
    const y = winStartY + (e.screenY - dragStartY);
    window.electronAPI?.saveWindowPosition(x, y);
  });
}

// ── Inicialización ────────────────────────────────────────────────────────────
async function init() {
  // Carga la configuración inicial desde el proceso Electron
  try {
    const cfg = await window.electronAPI?.getConfig();
    if (cfg) applyConfig(cfg);
  } catch (e) {
    console.warn('[Overlay] No se pudo cargar config inicial:', e);
  }

  // Suscribe a actualizaciones de configuración desde main
  window.electronAPI?.onConfigUpdated((cfg) => applyConfig(cfg));

  // Modo arrastre — activado/desactivado desde el panel de config
  window.electronAPI?.onDragModeChanged((enabled) => setLocked(!enabled));

  // Drag
  setupDrag();

  // Inicia la conexión WebSocket
  connect();

  // Observa cambios de tamaño del overlay
  const resizeObserver = new ResizeObserver(notifySize);
  resizeObserver.observe(el.overlay);
}

// Espera a que el DOM esté listo (debería estar, pero por robustez)
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
