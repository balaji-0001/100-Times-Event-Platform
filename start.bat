@echo off
title 100 TIMES Development Launcher
cd /d "%~dp0"

echo ========================================================
echo   Starting 100 TIMES (Backend + Frontend)
echo ========================================================

:: Use the project's local virtual environment Python
set "PYTHON_EXE=%~dp0artifacts\api-server\backend\venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=py.exe"
)

"%PYTHON_EXE%" start_dev.py
pause

