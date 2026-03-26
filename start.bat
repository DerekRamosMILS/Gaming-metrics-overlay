@echo off
title Overlay Videojuegos

:: ── Auto-elevación a administrador ────────────────────────────────────────────
:: Necesario para que PresentMon pueda leer FPS de otros procesos via ETW
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Solicitando permisos de administrador...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

:: Verifica que Python esté disponible
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no encontrado. Instala Python 3.10+ desde python.org
    pause
    exit /b 1
)

:: Va al directorio del script
cd /d "%~dp0"

:: Verifica dependencias de Python
python -c "import psutil, websockets, pystray, PIL" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Instalando dependencias de Python...
    pip install -r backend\requirements.txt
)

:: Verifica que node_modules exista en frontend
if not exist "frontend\node_modules" (
    echo [INFO] Instalando dependencias de Node.js...
    cd frontend
    npm install
    cd ..
)

echo [INFO] Iniciando Overlay Videojuegos...
echo [INFO] Presiona ALT+F10 para mostrar/ocultar el overlay
echo [INFO] Busca el icono OVL en el system tray para mas opciones
echo.

:: Lanza el backend sin ventana de consola (pythonw = python sin CMD)
start "" pythonw backend\main.py
