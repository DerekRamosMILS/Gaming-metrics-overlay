@echo off
title Setup - Overlay Videojuegos
echo ================================================
echo   Overlay Videojuegos - Setup
echo ================================================
echo.

cd /d "%~dp0"

:: ── Python ────────────────────────────────────────────────────────────────────
echo [1/4] Verificando Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no encontrado.
    echo         Descarga Python 3.10+ desde: https://python.org
    echo         Asegurate de marcar "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)
python --version
echo [OK] Python encontrado.
echo.

:: ── Dependencias Python ───────────────────────────────────────────────────────
echo [2/4] Instalando dependencias Python...
pip install -r backend\requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Fallo la instalacion de dependencias Python.
    pause
    exit /b 1
)
echo [OK] Dependencias Python instaladas.
echo.

:: ── Node.js ───────────────────────────────────────────────────────────────────
echo [3/4] Verificando Node.js...
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js no encontrado.
    echo         Descarga Node.js 18+ LTS desde: https://nodejs.org
    pause
    exit /b 1
)
node --version
echo [OK] Node.js encontrado.
echo.

:: ── Dependencias Node.js ─────────────────────────────────────────────────────
echo [4/4] Instalando dependencias Node.js (Electron)...
cd frontend
npm install
if %errorlevel% neq 0 (
    echo [ERROR] Fallo npm install.
    pause
    exit /b 1
)
cd ..
echo [OK] Dependencias Node.js instaladas.
echo.

:: ── Resumen ───────────────────────────────────────────────────────────────────
echo ================================================
echo   Setup completado exitosamente!
echo ================================================
echo.
echo Para iniciar el overlay:
echo   Doble click en start.bat
echo.
echo Para inicio automatico con Windows:
echo   Doble click en install_startup.bat
echo.
echo Para FPS (opcional):
echo   Lee tools\README_PRESENTMON.txt
echo.
echo Para temperaturas AMD/Intel (opcional):
echo   Lee tools\README_LHM.txt
echo.
pause
