@echo off
setlocal
cd /d "%~dp0"
title Agora Unit Tests

set PYTHONIOENCODING=utf-8

echo ============================================================
echo   Running All Unit Tests for Agora...
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_all_tests.py
) else (
    python run_all_tests.py
)

echo.
echo ============================================================
echo Tests finished.
echo ============================================================
pause
