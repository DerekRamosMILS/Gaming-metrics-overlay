@echo off
:: install_startup.bat
:: Registra el overlay para que inicie automáticamente con Windows
:: usando la carpeta Startup del usuario (NO requiere permisos de administrador)

title Instalar inicio automático - Overlay Videojuegos

cd /d "%~dp0"

:: Ruta a la carpeta Startup del usuario actual
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT_PATH=%STARTUP_DIR%\OverlayVideojuegos.lnk
set TARGET_PATH=%~dp0start.bat

echo [INFO] Creando acceso directo en: %STARTUP_DIR%

:: Usa PowerShell para crear el acceso directo (.lnk)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut('%SHORTCUT_PATH%');" ^
  "$s.TargetPath = '%TARGET_PATH%';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Overlay de métricas para videojuegos';" ^
  "$s.Save();"

if exist "%SHORTCUT_PATH%" (
    echo [OK] Inicio automatico configurado correctamente.
    echo [OK] El overlay iniciara con Windows en la proxima sesion.
) else (
    echo [ERROR] No se pudo crear el acceso directo.
    echo [INFO] Crea manualmente un acceso directo de start.bat en:
    echo        %STARTUP_DIR%
)

pause
