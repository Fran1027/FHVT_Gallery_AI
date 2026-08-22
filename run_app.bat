@echo off
title FHVT Studio Image Editor
cd /d "%~dp0"

:: Verificar entorno virtual
if not exist ".venv\Scripts\python.exe" (
    echo ========================================================
    echo Error: No se encontro el entorno virtual en .venv
    echo Por favor asegurese de tener la carpeta .venv configurada.
    echo ========================================================
    pause
    exit /b 1
)

:: Ejecutar con pythonw para no mantener la ventana de comandos abierta
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" main.py %*
) else (
    ".venv\Scripts\python.exe" main.py %*
)
