@echo off
:: Elimina el inicio automático con Windows

set SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\OverlayVideojuegos.lnk

if exist "%SHORTCUT_PATH%" (
    del "%SHORTCUT_PATH%"
    echo [OK] Inicio automatico eliminado.
) else (
    echo [INFO] No se encontro acceso directo de inicio automatico.
)

pause
