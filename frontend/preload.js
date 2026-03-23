/**
 * preload.js — Context Bridge seguro entre renderer y main process.
 *
 * SEGURIDAD: contextIsolation: true + sandbox: true.
 * El renderer NUNCA tiene acceso directo a Node.js o Electron APIs.
 * Solo los métodos expuestos aquí están disponibles.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // ── Configuración ────────────────────────────────────────────────────────
  getConfig: () => ipcRenderer.invoke('get-config'),
  updateConfig: (updates) => ipcRenderer.invoke('update-config', updates),

  // ── Control del overlay ──────────────────────────────────────────────────
  toggleOverlay: () => ipcRenderer.send('toggle-overlay'),
  setVisibility: (visible) => ipcRenderer.send('set-visibility', { visible }),
  openConfig: () => ipcRenderer.send('open-config'),
  resizeOverlay: (width, height) => ipcRenderer.send('resize-overlay', { width, height }),
  quit: () => ipcRenderer.send('quit-app'),
  getWindowPosition: () => ipcRenderer.invoke('get-window-position'),
  setWindowPosition: (x, y) => ipcRenderer.send('set-window-position', { x, y }),
  saveWindowPosition: (x, y) => ipcRenderer.send('save-window-position', { x, y }),
  setDragMode: (enabled) => ipcRenderer.send('set-drag-mode', { enabled }),
  onDragModeChanged: (callback) => {
    const handler = (_event, { enabled }) => callback(enabled);
    ipcRenderer.on('drag-mode-changed', handler);
    return () => ipcRenderer.removeListener('drag-mode-changed', handler);
  },

  // ── Suscripción a eventos ────────────────────────────────────────────────
  onConfigUpdated: (callback) => {
    const handler = (_event, config) => callback(config);
    ipcRenderer.on('config-updated', handler);
    return () => ipcRenderer.removeListener('config-updated', handler);
  },
});
