/**
 * main.js — Proceso principal de Electron
 *
 * Responsabilidades:
 * - Crear la ventana del overlay (transparente, always-on-top, click-through)
 * - Crear la ventana de configuración
 * - Gestionar el ciclo de vida de la aplicación
 * - Registrar hotkeys globales como backup del backend
 * - Posicionar el overlay según configuración
 */

const { app, BrowserWindow, globalShortcut, ipcMain, screen } = require('electron');
const path = require('path');
const fs = require('fs');

// Evita que errores de pipe rota (EPIPE) crasheen el proceso principal
process.stdout.on('error', (err) => { if (err.code === 'EPIPE') process.exit(0); });
process.stderr.on('error', (err) => { if (err.code === 'EPIPE') process.exit(0); });

// Nombre visible en Task Manager (debe llamarse antes de whenReady)
app.setName('OverlayMils');

// Suprime warnings cosméticos del cache de Chromium (antes de whenReady)
app.commandLine.appendSwitch('disable-gpu-shader-disk-cache');
app.commandLine.appendSwitch('disable-features', 'VaapiVideoDecoder');

// ── Configuración ─────────────────────────────────────────────────────────────
const CONFIG_PATH = path.join(__dirname, '..', 'config.json');

function loadConfig() {
  const defaults = {
    metrics: {
      fps: true, cpu_usage: true, cpu_temp: true,
      gpu_usage: true, gpu_temp: true, ram_usage: true, clock: true
    },
    display: {
      position: 'top-right',
      opacity: 0.85,
      font_size: 14,
      hotkey: 'Alt+F10',
      update_interval: 1000,
      visible: true,
      layout: 'horizontal'
    }
  };
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const raw = fs.readFileSync(CONFIG_PATH, 'utf-8');
      const parsed = JSON.parse(raw);
      return deepMerge(defaults, parsed);
    }
  } catch (e) {
    console.error('[Main] Error cargando config:', e.message);
  }
  return defaults;
}

function saveConfig(config) {
  try {
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2), 'utf-8');
  } catch (e) {
    console.error('[Main] Error guardando config:', e.message);
  }
}

function deepMerge(base, override) {
  const result = { ...base };
  for (const key of Object.keys(override)) {
    if (typeof result[key] === 'object' && typeof override[key] === 'object'
        && !Array.isArray(result[key])) {
      result[key] = deepMerge(result[key], override[key]);
    } else {
      result[key] = override[key];
    }
  }
  return result;
}

// ── Estado global ─────────────────────────────────────────────────────────────
let overlayWindow = null;
let configWindow = null;
let config = loadConfig();
let overlayVisible = config.display.visible;

// ── Posicionamiento del overlay ───────────────────────────────────────────────
const PADDING = 12; // px desde el borde de la pantalla

function getOverlayPosition(display, windowSize) {
  // Posición custom (guardada tras arrastrar) tiene prioridad sobre el preset
  if (Number.isInteger(config.display.x) && Number.isInteger(config.display.y)) {
    return { x: config.display.x, y: config.display.y };
  }

  const { width: sw, height: sh, x: sx, y: sy } = display.workArea;
  const { width: ww, height: wh } = windowSize;
  const position = config.display.position;

  const positions = {
    'top-left':     { x: sx + PADDING,                   y: sy + PADDING },
    'top-center':   { x: sx + Math.round((sw - ww) / 2), y: sy + PADDING },
    'top-right':    { x: sx + sw - ww - PADDING,         y: sy + PADDING },
    'bottom-left':  { x: sx + PADDING,                   y: sy + sh - wh - PADDING },
    'bottom-center':{ x: sx + Math.round((sw - ww) / 2), y: sy + sh - wh - PADDING },
    'bottom-right': { x: sx + sw - ww - PADDING,         y: sy + sh - wh - PADDING },
  };

  return positions[position] || positions['top-right'];
}

// ── Ventana del Overlay ───────────────────────────────────────────────────────
function createOverlayWindow() {
  const primaryDisplay = screen.getPrimaryDisplay();
  // Ancho inicial generoso para que el layout horizontal no se corte antes del resize
  const isHorizontal = config.display.layout === 'horizontal';
  const overlaySize = { width: isHorizontal ? 800 : 220, height: 220 };
  const pos = getOverlayPosition(primaryDisplay, overlaySize);

  overlayWindow = new BrowserWindow({
    // Geometría inicial; se ajusta dinámicamente por el renderer
    width: overlaySize.width,
    height: overlaySize.height,
    x: pos.x,
    y: pos.y,

    // Transparencia y apariencia
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    roundedCorners: false,

    // Comportamiento de ventana
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    movable: false,    // Se mueve programáticamente desde config
    focusable: false,  // No toma el foco del juego

    // Seguridad y aislamiento
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      // sandbox: false para permitir WebSocket a localhost desde el renderer
      sandbox: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  // Click-through: los clicks pasan al juego subyacente
  // forward: true → el renderer puede recibir eventos de mouse (para drag futuro)
  overlayWindow.setIgnoreMouseEvents(true, { forward: true });

  // Encima de aplicaciones fullscreen (ej: juegos)
  // 'screen-saver' es el nivel más alto disponible en Windows
  overlayWindow.setAlwaysOnTop(true, 'screen-saver');

  // Evita que aparezca en el taskbar de Windows
  overlayWindow.setSkipTaskbar(true);

  // Opacidad inicial
  overlayWindow.setOpacity(config.display.opacity);

  overlayWindow.loadFile(path.join(__dirname, 'renderer', 'overlay.html'));

  // Oculto por defecto si la config dice invisible
  if (!overlayVisible) {
    overlayWindow.hide();
  }

  overlayWindow.on('closed', () => {
    overlayWindow = null;
  });

  // En desarrollo, abre DevTools (sin afectar el overlay)
  if (process.argv.includes('--debug')) {
    overlayWindow.webContents.openDevTools({ mode: 'detach' });
  }

  console.log('[Main] Ventana overlay creada');
}

// ── Ventana de Configuración ──────────────────────────────────────────────────
function createConfigWindow() {
  if (configWindow) {
    configWindow.focus();
    return;
  }

  configWindow = new BrowserWindow({
    width: 480,
    height: 680,
    minWidth: 420,
    minHeight: 500,
    title: 'Overlay Videojuegos — Configuración',
    frame: true,
    transparent: false,
    alwaysOnTop: false,
    resizable: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  configWindow.setMenuBarVisibility(false);
  configWindow.loadFile(path.join(__dirname, 'renderer', 'config.html'));

  // Auto-reload si el renderer se congela
  configWindow.webContents.on('did-stop-responding', () => {
    console.warn('[Config] Ventana congelada — recargando...');
    configWindow.webContents.reload();
  });

  configWindow.on('closed', () => {
    configWindow = null;
    // Asegura que el overlay vuelve a ser click-through al cerrar config
    if (overlayWindow) {
      overlayWindow.setIgnoreMouseEvents(true, { forward: true });
      overlayWindow.webContents.send('drag-mode-changed', { enabled: false });
    }
  });
}

// ── Toggle de visibilidad ─────────────────────────────────────────────────────
function toggleOverlay() {
  if (!overlayWindow) return;
  overlayVisible = !overlayVisible;
  config.display.visible = overlayVisible;
  saveConfig(config);

  if (overlayVisible) {
    overlayWindow.show();
  } else {
    overlayWindow.hide();
  }
  console.log(`[Main] Overlay ${overlayVisible ? 'visible' : 'oculto'}`);
}

function setOverlayVisible(visible) {
  overlayVisible = visible;
  config.display.visible = visible;
  if (overlayWindow) {
    if (visible) overlayWindow.show();
    else overlayWindow.hide();
  }
}

// ── Reposicionar overlay ──────────────────────────────────────────────────────
function repositionOverlay() {
  if (!overlayWindow) return;
  const display = screen.getPrimaryDisplay();
  const bounds = overlayWindow.getBounds();
  const pos = getOverlayPosition(display, { width: bounds.width, height: bounds.height });
  overlayWindow.setPosition(pos.x, pos.y);
}

// ── IPC handlers (comunicación con renderer) ──────────────────────────────────
function setupIPC() {
  // Renderer solicita la configuración actual
  ipcMain.handle('get-config', () => config);

  // Renderer actualiza configuración
  ipcMain.handle('update-config', (_event, updates) => {
    config = deepMerge(config, updates);
    // Si el usuario elige un preset de posición, borra la posición custom del drag
    if (updates.display && updates.display.position) {
      delete config.display.x;
      delete config.display.y;
    }
    saveConfig(config);

    // Aplica cambios inmediatos en la ventana
    if (overlayWindow) {
      overlayWindow.setOpacity(config.display.opacity);
    }
    repositionOverlay();

    // Notifica a todas las ventanas del cambio
    if (overlayWindow) {
      overlayWindow.webContents.send('config-updated', config);
    }
    if (configWindow) {
      configWindow.webContents.send('config-updated', config);
    }

    return config;
  });

  // Toggle desde renderer
  ipcMain.on('toggle-overlay', () => toggleOverlay());

  // Ajustar tamaño del overlay (el renderer calcula su tamaño real)
  ipcMain.on('resize-overlay', (_event, { width, height }) => {
    if (overlayWindow) {
      overlayWindow.setSize(Math.ceil(width), Math.ceil(height));
      // No reposicionar si hay posición custom guardada
      if (!Number.isInteger(config.display.x)) {
        repositionOverlay();
      }
    }
  });

  // Posición de la ventana (para el drag)
  ipcMain.handle('get-window-position', () => {
    if (!overlayWindow) return { x: 0, y: 0 };
    const [x, y] = overlayWindow.getPosition();
    return { x, y };
  });

  ipcMain.on('set-window-position', (_event, { x, y }) => {
    if (overlayWindow) {
      overlayWindow.setPosition(Math.round(x), Math.round(y));
    }
  });

  ipcMain.on('save-window-position', (_event, { x, y }) => {
    if (overlayWindow) {
      overlayWindow.setPosition(Math.round(x), Math.round(y));
    }
    config.display.x = Math.round(x);
    config.display.y = Math.round(y);
    saveConfig(config);
    console.log(`[Main] Posición guardada: ${Math.round(x)}, ${Math.round(y)}`);
  });

  // Modo arrastre del overlay (activado desde el panel de config)
  ipcMain.on('set-drag-mode', (_event, { enabled }) => {
    if (overlayWindow) {
      overlayWindow.setIgnoreMouseEvents(!enabled, { forward: !enabled });
      overlayWindow.webContents.send('drag-mode-changed', { enabled });
    }
  });

  // Abrir ventana de configuración
  ipcMain.on('open-config', () => createConfigWindow());

  // Visibilidad desde backend WebSocket (relayed por renderer)
  ipcMain.on('set-visibility', (_event, { visible }) => {
    setOverlayVisible(visible);
  });

  // Salida completa — cierra Electron (el backend detecta el cierre y termina también)
  ipcMain.on('quit-app', () => {
    console.log('[Main] Salida solicitada desde overlay');
    globalShortcut.unregisterAll();
    app.quit();
  });

}

// ── Hotkeys globales ──────────────────────────────────────────────────────────
function registerHotkeys() {
  // Normaliza el hotkey de la config al formato de Electron
  const hotkey = (config.display.hotkey || 'Alt+F10')
    .split('+')
    .map(k => k.charAt(0).toUpperCase() + k.slice(1).toLowerCase())
    .join('+')
    .replace('Alt', 'Alt')
    .replace('F10', 'F10');

  try {
    const registered = globalShortcut.register(hotkey, () => {
      console.log(`[Main] Hotkey ${hotkey} activado`);
      toggleOverlay();
    });
    if (registered) {
      console.log(`[Main] Hotkey registrado: ${hotkey}`);
    } else {
      console.warn(`[Main] No se pudo registrar hotkey: ${hotkey}`);
    }
  } catch (e) {
    console.error('[Main] Error registrando hotkey:', e.message);
  }
}

// ── Watchdog: cierra Electron cuando el backend Python muere ──────────────────
// Verifica cada 3 s si el puerto WebSocket sigue activo.
// Cuando detecta que el backend (que estaba vivo) deja de responder → process.exit(0).
// Funciona desde el proceso PRINCIPAL de Electron, independientemente de renderers e IPC.
function startBackendWatchdog() {
  const net = require('net');
  const WS_PORT = 29874;
  let wasAlive = false;

  setInterval(() => {
    const socket = new net.Socket();
    socket.setTimeout(1000);

    socket.on('connect', () => {
      wasAlive = true;
      socket.destroy();
    });

    socket.on('error', () => {
      socket.destroy();
      if (wasAlive) {
        console.log('[Main] Backend Python muerto — cerrando Electron');
        process.exit(0);
      }
    });

    socket.on('timeout', () => {
      socket.destroy();
      if (wasAlive) {
        console.log('[Main] Backend Python timeout — cerrando Electron');
        process.exit(0);
      }
    });

    socket.connect(WS_PORT, '127.0.0.1');
  }, 1500);
}

// ── Ciclo de vida de la app ───────────────────────────────────────────────────
app.whenReady().then(() => {
  setupIPC();
  createOverlayWindow();
  registerHotkeys();
  // Empieza el watchdog 1.5 s después de arrancar
  setTimeout(startBackendWatchdog, 1500);
  console.log('[Main] Overlay Videojuegos iniciado');
});

app.on('window-all-closed', () => {
  // En Windows: la app sigue corriendo en background (el backend la gestiona)
  // No hacemos app.quit() aquí
});

app.on('will-quit', () => {
  // Protección: globalShortcut solo existe si la app llegó a estar "ready"
  if (app.isReady()) {
    globalShortcut.unregisterAll();
  }
});

// Previene que Electron muestre ventana adicional si se lanza dos veces
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  // Segunda instancia: simplemente salimos sin pasar por "ready"
  app.quit();
} else {
  app.on('second-instance', () => {
    // Si se intenta abrir una segunda instancia, muestra la config
    createConfigWindow();
  });
}
