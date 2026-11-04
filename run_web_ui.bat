@echo off
setlocal
cd /d "%~dp0"
title Agora Web UI - Streamlit

set PYTHONIOENCODING=utf-8

if not exist ".venv\Scripts\streamlit.exe" (
    echo [ERROR] Streamlit is not installed in .venv.
    pause
    exit /b 1
)

echo ============================================================
echo   Starting Agora Web UI (Streamlit)...
echo   URL: http://localhost:8501
echo ============================================================
echo.

".venv\Scripts\streamlit.exe" run app.py

echo.
echo Process finished.
pause
