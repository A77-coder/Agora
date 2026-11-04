@echo off
setlocal
cd /d "%~dp0"
title Agora Dialogue Simulation

set PYTHONIOENCODING=utf-8

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found.
    pause
    exit /b 1
)

echo Starting Agora Dialogue Simulation...
echo.
".venv\Scripts\python.exe" dialogue_simulation.py

echo.
echo ============================================================
echo Process finished.
echo ============================================================
pause
