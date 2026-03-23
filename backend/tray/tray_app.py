"""
Icono en el System Tray de Windows.

Proporciona:
- Icono visible en la bandeja del sistema
- Menú contextual para controlar el overlay
- Opción de abrir configuración
- Opción de salir de la aplicación

El icono se genera dinámicamente con Pillow para evitar dependencias de assets.
"""
import threading
import logging
from typing import Callable, Optional

import pystray  # type: ignore
from PIL import Image, ImageDraw, ImageFont  # type: ignore

logger = logging.getLogger(__name__)


def _create_tray_icon(visible: bool = True) -> Image.Image:
    """
    Genera el icono del tray dinámicamente.
    Un cuadrado con texto "OVL" en verde (visible) o gris (oculto).
    """
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fondo redondeado
    color = (30, 215, 96, 255) if visible else (100, 100, 100, 255)  # Verde/Gris
    draw.rounded_rectangle([2, 2, size - 2, size - 2], radius=12, fill=color)

    # Texto "OVL"
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except (IOError, OSError):
        font = ImageFont.load_default()

    text = "OVL"
    # Centrar texto
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) // 2
    y = (size - text_h) // 2 - 2
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    return img


class TrayApp:
    """
    Gestiona el icono del system tray y su menú contextual.
    Corre en su propio hilo para no bloquear el event loop de asyncio.
    """

    def __init__(
        self,
        on_toggle: Optional[Callable] = None,
        on_quit: Optional[Callable] = None,
        on_open_config: Optional[Callable] = None,
    ):
        self._on_toggle = on_toggle
        self._on_quit = on_quit
        self._on_open_config = on_open_config
        self._visible = True
        self._icon: Optional[pystray.Icon] = None

    def _build_menu(self) -> pystray.Menu:
        """Construye el menú contextual del tray."""
        toggle_label = "Ocultar overlay" if self._visible else "Mostrar overlay"
        return pystray.Menu(
            pystray.MenuItem(toggle_label, self._handle_toggle, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Configuración", self._handle_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self._handle_quit),
        )

    def _handle_toggle(self, icon, item) -> None:
        self._visible = not self._visible
        icon.icon = _create_tray_icon(self._visible)
        icon.menu = self._build_menu()
        if self._on_toggle:
            self._on_toggle(self._visible)

    def _handle_quit(self, icon, item) -> None:
        # Mata Python inmediatamente — el watchdog de Electron detecta el puerto
        # muerto y cierra Electron en ~1.5 s sin necesidad de señalización adicional
        import os
        os._exit(0)

    def _handle_config(self, icon, item) -> None:
        if self._on_open_config:
            self._on_open_config()

    def update_visibility(self, visible: bool) -> None:
        """Sincroniza el estado del icono con la visibilidad actual."""
        self._visible = visible
        if self._icon:
            self._icon.icon = _create_tray_icon(visible)
            self._icon.menu = self._build_menu()

    def run(self) -> None:
        """Bloquea el hilo actual ejecutando el loop del tray."""
        self._icon = pystray.Icon(
            name="overlay_videojuegos",
            icon=_create_tray_icon(self._visible),
            title="Overlay Videojuegos",
            menu=self._build_menu(),
        )
        logger.info("[Tray] Icono iniciado en system tray")
        self._icon.run()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
