/**
 * config.js — Renderer de la ventana de configuración
 */
'use strict';

let currentConfig = null;

const inputs = {
  cpuUsage:   document.getElementById('cfg-cpu-usage'),
  cpuTemp:    document.getElementById('cfg-cpu-temp'),
  gpuUsage:   document.getElementById('cfg-gpu-usage'),
  gpuTemp:    document.getElementById('cfg-gpu-temp'),
  ram:        document.getElementById('cfg-ram'),
  clock:      document.getElementById('cfg-clock'),
  theme:      document.getElementById('cfg-theme'),
  layout:     document.getElementById('cfg-layout'),
  position:   document.getElementById('cfg-position'),
  opacity:    document.getElementById('cfg-opacity'),
  fontSize:   document.getElementById('cfg-font-size'),
  interval:   document.getElementById('cfg-interval'),
  hotkey:     document.getElementById('cfg-hotkey'),
  colorText:  document.getElementById('cfg-color-text'),
  colorClock: document.getElementById('cfg-color-clock'),
  colorGood:  document.getElementById('cfg-color-good'),
  colorWarn:  document.getElementById('cfg-color-warn'),
  colorCrit:  document.getElementById('cfg-color-crit'),
};

const displays = {
  opacity:    document.getElementById('opacity-display'),
  fontSize:   document.getElementById('font-size-display'),
};

const statusEl = document.getElementById('status');

function populateUI(config) {
  const m = config.metrics || {};
  const d = config.display || {};

  inputs.cpuUsage.checked = m.cpu_usage !== false;
  inputs.cpuTemp.checked  = m.cpu_temp !== false;
  inputs.gpuUsage.checked = m.gpu_usage !== false;
  inputs.gpuTemp.checked  = m.gpu_temp !== false;
  inputs.ram.checked      = m.ram_usage !== false;
  inputs.clock.checked    = m.clock !== false;

  inputs.theme.value      = d.theme  || 'default';
  inputs.layout.value     = d.layout || 'horizontal';
  const c = d.colors || {};
  inputs.colorText.value  = c.text  || '#2ecc71';
  inputs.colorClock.value = c.clock || c.text || '#2ecc71';
  inputs.colorGood.value  = c.good  || '#2ecc71';
  inputs.colorWarn.value  = c.warn  || '#f39c12';
  inputs.colorCrit.value  = c.crit  || '#e74c3c';
  inputs.position.value   = d.position || 'top-right';
  inputs.opacity.value    = Math.round((d.opacity || 0.85) * 100);
  inputs.fontSize.value   = d.font_size || 14;
  inputs.interval.value   = String(d.update_interval || 1000);
  inputs.hotkey.value     = d.hotkey || 'alt+f10';

  updateDisplays();
}

function updateDisplays() {
  displays.opacity.textContent  = `${inputs.opacity.value}%`;
  displays.fontSize.textContent = `${inputs.fontSize.value}px`;
}

function collectConfig() {
  return {
    metrics: {
      cpu_usage: inputs.cpuUsage.checked,
      cpu_temp:  inputs.cpuTemp.checked,
      gpu_usage: inputs.gpuUsage.checked,
      gpu_temp:  inputs.gpuTemp.checked,
      ram_usage: inputs.ram.checked,
      clock:     inputs.clock.checked,
    },
    display: {
      theme:           inputs.theme.value,
      layout:          inputs.layout.value,
      position:        inputs.position.value,
      opacity:         parseInt(inputs.opacity.value, 10) / 100,
      font_size:       parseInt(inputs.fontSize.value, 10),
      update_interval: parseInt(inputs.interval.value, 10),
      hotkey:          inputs.hotkey.value.trim() || 'alt+f10',
      colors: {
        text:  inputs.colorText.value,
        clock: inputs.colorClock.value,
        good:  inputs.colorGood.value,
        warn:  inputs.colorWarn.value,
        crit:  inputs.colorCrit.value,
      },
    }
  };
}

function showStatus(msg, isError = false) {
  statusEl.style.color = isError ? '#e74c3c' : '#2ecc71';
  statusEl.textContent = msg;
  setTimeout(() => { statusEl.textContent = ''; }, 3000);
}

// ── Modo arrastre del overlay ─────────────────────────────────────────────────
let dragModeActive = false;
const btnDragToggle = document.getElementById('btn-drag-toggle');

if (btnDragToggle) {
  btnDragToggle.addEventListener('click', () => {
    dragModeActive = !dragModeActive;
    window.electronAPI?.setDragMode(dragModeActive);
    if (dragModeActive) {
      btnDragToggle.textContent = '🔒 Bloquear';
      btnDragToggle.style.background = '#e94560';
      btnDragToggle.style.color = 'white';
    } else {
      btnDragToggle.textContent = '🔓 Mover';
      btnDragToggle.style.background = '';
      btnDragToggle.style.color = '';
    }
  });
}

// ── Event listeners ───────────────────────────────────────────────────────────
inputs.opacity.addEventListener('input', updateDisplays);
inputs.fontSize.addEventListener('input', updateDisplays);

const btnSave = document.getElementById('btn-save');
btnSave.addEventListener('click', async () => {
  if (btnSave.disabled) return;
  btnSave.disabled = true;
  const newConfig = collectConfig();
  try {
    await window.electronAPI?.updateConfig(newConfig);
    showStatus('✓ Configuración guardada');
  } catch (e) {
    showStatus('Error al guardar', true);
  } finally {
    btnSave.disabled = false;
  }
});

document.getElementById('btn-cancel').addEventListener('click', () => {
  window.close();
});

window.electronAPI?.onConfigUpdated((cfg) => {
  currentConfig = cfg;
  populateUI(cfg);
});

// Inicializa con la configuración actual
async function init() {
  try {
    currentConfig = await window.electronAPI?.getConfig();
    if (currentConfig) populateUI(currentConfig);
  } catch (e) {
    showStatus('Error cargando configuración', true);
  }
}

init();
