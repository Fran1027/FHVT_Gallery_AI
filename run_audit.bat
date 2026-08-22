@echo off
chcp 65001 > nul
setlocal

cd /d "%~dp0"
set "VENV_PYTHON=.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] No se encontro el entorno virtual en: %VENV_PYTHON%
    pause
    exit /b 1
)

echo ===============================================================================
echo   FHVT STUDIO IMAGE EDITOR - AUDITORIA ARQUITECTURAL Y DIAGNOSTICO EN VIVO
echo ===============================================================================
echo.

"%VENV_PYTHON%" "audit_tools\run_audit_suite.py"

echo.
pause
