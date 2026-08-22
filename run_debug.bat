@echo off
title FHVT Studio Image Editor (Modo Depuracion)
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ========================================================
    echo Error: No se encontro el entorno virtual en .venv
    echo Por favor configure el entorno virtual antes de continuar.
    echo ========================================================
    pause
    exit /b 1
)

echo Iniciando FHVT Studio Image Editor en modo consola...
".venv\Scripts\python.exe" main.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo La aplicacion finalizo con errores.
    pause
)
